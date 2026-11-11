from rest_framework import serializers

from catalog.models import Category, ServiceName


class CategorySerializer(serializers.ModelSerializer):
    in_use = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Category
        fields = ("id", "name", "is_preset", "in_use")
        read_only_fields = fields


class CategoryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=Category._meta.get_field("name").max_length)


class ServiceNameSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    in_use = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = ServiceName
        fields = ("id", "name", "category", "category_name", "is_preset", "in_use")
        read_only_fields = fields


class ServiceNameCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=ServiceName._meta.get_field("name").max_length)
    category = serializers.IntegerField()
