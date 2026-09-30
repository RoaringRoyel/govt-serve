from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .rag import RAGService


class QuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=500)


class AskView(APIView):
    rag = RAGService()

    @extend_schema(request=QuestionSerializer, responses={200: dict})
    def post(self, request):
        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.rag.answer(serializer.validated_data["question"], user=request.user))
