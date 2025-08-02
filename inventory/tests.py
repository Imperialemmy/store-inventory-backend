from django.test import TestCase
from .models import Brand, Category, Size, Ware, WareVariant
# Create your tests here.

class BrandModelTest(TestCase):

    def test_brand_creation(self):
        brand1 = Brand.objects.create(name="Nike")
        self.assertEqual(brand1.name, "Nike")  # checks if the name is set correctly
        self.assertEqual(str(brand1), "Nike")  # checks the __str__ method

class CategoryModelTest(TestCase):

    def test_category_creation(self):
        category1 = Category.objects.create(name="Footwear")
        self.assertEqual(category1.name, "Footwear")  # checks if the name is set correctly
        self.assertEqual(str(category1), "Footwear")  # checks the __str__ method
