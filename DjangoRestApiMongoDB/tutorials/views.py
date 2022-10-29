from django.shortcuts import render

from django.http.response import JsonResponse
from rest_framework.parsers import JSONParser
from rest_framework import status
from django.conf import settings

import redis
import copy
import pickle

from tutorials.models import Tutorial
from tutorials.serializers import TutorialSerializer
from rest_framework.decorators import api_view


# Connect to our Redis instance
redis_instance = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0)


def redis_sync():
    print(f'Count Keys [{len(redis_instance.keys())}/{settings.MAX_OBJECTS_IN_CACHE}]')

    if len(redis_instance.keys()) >= settings.MAX_OBJECTS_IN_CACHE:
        for key in redis_instance.keys():
            redis_record = pickle.loads(redis_instance.get(key))

            if redis_record['method'] == 'GET':
                redis_instance.delete(key)
                print(f'Method: [GET]; Key: [{key}]')
            elif redis_record['method'] == 'POST':
                tutorial_data = copy.deepcopy(redis_record)
                del tutorial_data['method']
                tutorial_serializer = TutorialSerializer(data=tutorial_data)
                if tutorial_serializer.is_valid():
                    tutorial_serializer.save()
                redis_instance.delete(key)
                print(f'Method: [POST]; Key: [{key}]')
            elif redis_record['method'] == 'PUT':
                tutorial_data = copy.deepcopy(redis_record)
                old_value = Tutorial.objects.get(pk=int(key))
                del tutorial_data['method']
                tutorial_serializer = TutorialSerializer(old_value, data=tutorial_data)
                if tutorial_serializer.is_valid():
                    tutorial_serializer.save()
                redis_instance.delete(key)
                print(f'Method: [PUT]; Key: [{key}]')
            elif redis_record['method'] == 'DELETE':
                tutorial = Tutorial.objects.get(pk=int(key))
                tutorial.delete()
                redis_instance.delete(key)
                print(f'Method: [DELETE]; Key: [{key}]')


@api_view(['GET', 'POST', 'DELETE'])
def tutorial_list(request):
    redis_sync()

    if request.method == 'GET':
        tutorials = Tutorial.objects.all()

        title = request.GET.get('title', None)
        if title is not None:
            tutorials = tutorials.filter(title__icontains=title)

        tutorials_serializer = TutorialSerializer(tutorials, many=True)
        return JsonResponse(tutorials_serializer.data, safe=False)
        # 'safe=False' for objects serialization
    elif request.method == 'POST':
            tutorial_data = JSONParser().parse(request)
            tutorial_serializer = TutorialSerializer(data=tutorial_data)
            if tutorial_serializer.is_valid():
                # tutorial_serializer.save()
                redis_record = tutorial_data
                redis_record['method'] = 'POST'
                redis_instance.set(tutorial_data['title'], pickle.dumps(redis_record))
                return JsonResponse(tutorial_serializer.data, status=status.HTTP_201_CREATED)
            return JsonResponse(tutorial_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        for key in redis_instance.keys():
            redis_instance.delete(key)

        count = Tutorial.objects.all().delete()
        return JsonResponse({'message': '{} Tutorials were deleted successfully!'.format(count[0])},
                            status=status.HTTP_204_NO_CONTENT)

@api_view(['GET', 'PUT', 'DELETE'])
def tutorial_detail(request, pk):
    redis_sync()

    # find tutorial by pk (id)
    try:
        if redis_instance.get(pk) is None:
            tutorial = Tutorial.objects.get(pk=pk)
            redis_record = {
                'description': tutorial.description,
                'published': tutorial.published,
                'title': tutorial.title,
                'method': ''
            }
            redis_instance.set(str(pk), pickle.dumps(redis_record))
        else:
            redis_record = pickle.loads(redis_instance.get(pk))

        if redis_record['method'] == 'DELETE':
            return JsonResponse({'message': 'The tutorial does not exist'}, status=status.HTTP_404_NOT_FOUND)

    except Tutorial.DoesNotExist:
        return JsonResponse({'message': 'The tutorial does not exist'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        # tutorial_serializer = TutorialSerializer(redis_record['tutorial'])
        if not  redis_record['method']:
            redis_record['method'] = 'GET'
            redis_instance.set(pk, pickle.dumps(redis_record))
        return JsonResponse(redis_record)
    elif request.method == 'PUT':
        tutorial_data = JSONParser().parse(request)
        tutorial_serializer = TutorialSerializer(redis_record, data=tutorial_data)
        if tutorial_serializer.is_valid():
            #tutorial_serializer.save()
            redis_record = copy.deepcopy(tutorial_data)
            redis_record['method'] = 'PUT'
            redis_instance.set(pk, pickle.dumps(redis_record))
            return JsonResponse(redis_record)
        return JsonResponse(tutorial_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        redis_record['method'] = 'DELETE'
        redis_instance.set(pk, pickle.dumps(redis_record))
        return JsonResponse({'message': 'Tutorial was deleted successfully!'}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
def tutorial_list_published(request):
    tutorials = Tutorial.objects.filter(published=True)

    if request.method == 'GET':
        tutorials_serializer = TutorialSerializer(tutorials, many=True)
        return JsonResponse(tutorials_serializer.data, safe=False)
