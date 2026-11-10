from rest_framework.pagination import PageNumberPagination


class OngshoPageNumberPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data, extra=None):
        response = super().get_paginated_response(data)
        if extra:
            response.data.update(extra)
        return response
