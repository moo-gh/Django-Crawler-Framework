import logging
import redis
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.pagination import PageNumberPagination

from agency import serializer as age_serializer
from agency.models import Agency, Page, Report
from crawler.messages import msg


logger = logging.getLogger(__name__)


class PostPagination(PageNumberPagination):
    page_size = 10


class AgencyView(viewsets.ModelViewSet):
    def create(self, request, *_args, **_kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            response_data = {
                "status": "200",
                "message": msg["fa"]["agency"]["success_agency_created"],
                "data": serializer.data,
            }
            print(serializer.data["id"], serializer.data["website"])
        else:
            response_data = {
                "status": "400",
                "message": msg["fa"]["agency"]["failed_agency_created"],
                "data": serializer.errors,
            }
        return Response(response_data)

    def update(self, request, *args, _version=None, pk=None, **kwargs):
        instance = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.serializer_class(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            response_data = {
                "status": "200",
                "message": msg["fa"]["agency"]["success_agency_updated"],
                "data": serializer.data,
            }
        else:
            response_data = {
                "status": "400",
                "message": msg["fa"]["agency"]["failed_agency_updated"],
                "data": serializer.errors,
            }
        return Response(response_data)

    def retrieve(self, *args, _request=None, _version=None, pk=None, **kwargs):
        try:
            agency = Agency.objects.get(pk=pk)
        except Agency.DoesNotExist:
            return Response(
                {"status": "400", "message": msg["fa"]["agency"]["agency_not_found"]}
            )
        serializer = age_serializer.AgencySerializer(agency)
        data = {}
        data["status"] = "200"
        data["message"] = msg["fa"]["agency"]["agency_found"]
        data["data"] = serializer.data
        return Response(data)

    def destroy(self, *args, _request=None, _version=None, pk=None, **kwargs):
        try:
            agency = Agency.objects.get(pk=pk)
        except Agency.DoesNotExist:
            return Response(
                {"status": "400", "message": msg["fa"]["agency"]["agency_not_found"]}
            )
        agency.deleted_at = timezone.localtime()
        agency.save()
        response_data = {
            "status": "200",
            "message": msg["fa"]["agency"]["success_agency_deleted"],
            "data": "",
        }
        return Response(response_data)

    queryset = Agency.objects.filter(deleted_at=None).order_by("id")
    serializer_class = age_serializer.AgencySerializer


class PageView(viewsets.ModelViewSet):
    queryset = Page.objects.all().order_by("id")
    serializer_class = age_serializer.PageSerializer

    def create(self, request, *_args, **_kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            response_data = {
                "status": "200",
                "message": msg["fa"]["page"]["success_page_created"],
                "data": serializer.data,
            }
        else:
            response_data = {
                "status": "400",
                "message": msg["fa"]["page"]["failed_page_created"],
                "data": serializer.errors,
            }
        return Response(response_data)

    def retrieve(self, *args, _request=None, _version=None, pk=None, **kwargs):
        try:
            page = Page.objects.get(pk=pk)
        except Page.DoesNotExist:
            return Response(
                {"status": "400", "message": msg["fa"]["page"]["page_not_found"]}
            )
        serializer = age_serializer.PageSerializer(page)
        data = {}
        data["status"] = "200"
        data["message"] = msg["fa"]["page"]["page_found"]
        data["data"] = serializer.data
        return Response(data)

    def update(self, request, *args, _version=None, pk=None, **kwargs):
        instance = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.serializer_class(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            response_data = {
                "status": "200",
                "message": msg["fa"]["page"]["success_page_updated"],
                "data": serializer.data,
            }
        else:
            response_data = {
                "status": "400",
                "message": msg["fa"]["page"]["failed_page_updated"],
                "data": serializer.errors,
            }
        return Response(response_data)

    def destroy(self, *args, _request=None, _version=None, pk=None, **kwargs):
        try:
            page = Page.objects.get(pk=pk)
        except Page.DoesNotExist:
            return Response(
                {"status": "400", "message": msg["fa"]["page"]["page_not_found"]}
            )
        page.deleted_at = timezone.localtime()
        page.save()
        response_data = {
            "status": "200",
            "message": msg["fa"]["page"]["success_page_deleted"],
            "data": "",
        }
        return Response(response_data)


@api_view(["GET"])
def agency_pages(_request, _version, agency_id):
    pages = Page.objects.filter(agency_id=agency_id)
    serializer = age_serializer.PageSerializer(pages, many=True)
    result = {}
    result["status"] = "200"
    result["message"] = msg["fa"]["agency"]["retrieved_pages"]
    result["data"] = serializer.data
    return Response(result)


@api_view(["GET"])
def crawl(_request, _version):
    Page.objects.all().update(last_crawl=None)
    return Response(
        {"status": "200", "message": msg["fa"]["crawl"]["success_crawl_all"]}
    )


@api_view(["GET"])
def crawl_page(_request, _version, page_id):
    Page.objects.filter(id=page_id).update(last_crawl=None)
    return Response(
        {"status": "200", "message": msg["fa"]["crawl"]["success_crawl_page"]}
    )


@api_view(["GET"])
def crawl_agency_active_all(_request, _version):
    Agency.objects.update(status=True)
    return Response(
        {
            "status": "200",
            "message": msg["fa"]["crawl"]["success_crawl_agency_activeAll"],
        }
    )


@api_view(["GET"])
def crawl_agency_disable_all(_request, _version):
    Agency.objects.update(status=False)
    return Response(
        {
            "status": "200",
            "message": msg["fa"]["crawl"]["success_crawl_agency_disableAll"],
        }
    )


def crawl_agency_none_lats_crawl(agency_id):
    Agency.objects.filter(id=agency_id).update(status=True)
    Page.objects.filter(agency=agency_id).update(last_crawl=None, status=True)
    x = Page.objects.filter(agency=agency_id).values("id")
    x = Report.objects.filter(page__in=x, status="pending").update(status="failed")


@api_view(["GET"])
def crawl_agency(_request, _version, agency_id):
    crawl_agency_none_lats_crawl(agency_id)
    return Response(
        {"status": "200", "message": msg["fa"]["crawl"]["success_crawl_agency"]}
    )


@api_view(["GET"])
def crawl_memory_reset(_request, _version):
    redis_news = redis.StrictRedis(host="crawler-redis", port=6379, db=0)
    redis_duplicate_checker = redis.StrictRedis(host="crawler-redis", port=6379, db=1)
    redis_duplicate_checker.flushall()
    redis_news.flushall()
    return JsonResponse(
        {"status": "200", "message": msg["fa"]["crawl"]["success_crawl_memory_reset"]},
        status=200,
    )


@api_view(["GET"])
def crawl_news_memory_list(_request, _version):
    redis_news = redis.StrictRedis(host="crawler-redis", port=6379, db=0)
    return Response({"news_keys": redis_news.keys("*")})


@api_view(["GET"])
def crawl_links_memory_list(_request, _version):
    redis_duplicate_checker = redis.StrictRedis(host="crawler-redis", port=6379, db=1)
    return Response({"link_keys": redis_duplicate_checker.keys("*")})


def reset_agency_memory(agency_id):
    agency = Agency.objects.get(id=agency_id)
    redis_news = redis.StrictRedis(host="crawler-redis", port=6379, db=0)
    redis_duplicate_checker = redis.StrictRedis(host="crawler-redis", port=6379, db=1)
    counter_links = 0
    for key in redis_duplicate_checker.scan_iter("*" + str(agency.website) + "*"):
        redis_duplicate_checker.delete(key)
        counter_links += 1
    counter_news = 0
    for key in redis_news.scan_iter("*" + str(agency.website) + "*"):
        redis_news.delete(key)
        counter_news += 1
    return counter_links, counter_news


@api_view(["GET"])
def crawl_agency_reset_memory(_request, _version, agency_id):
    counter_links, counter_news = reset_agency_memory(agency_id)
    return Response(
        {
            "number_of_links_deleted": counter_links,
            "number_of_news_deleted": counter_news,
        }
    )


@api_view(["GET"])
def crawl_agency_reset_memory_and_crawl(_request, _version, agency_id):
    crawl_agency_none_lats_crawl(agency_id)
    counter_links, counter_news = reset_agency_memory(agency_id)
    return Response(
        {
            "number_of_links_deleted": counter_links,
            "number_of_news_deleted": counter_news,
        }
    )


class ReportView(ReadOnlyModelViewSet):
    pagination_class = PostPagination

    def list(self, *args, _request=None, _version=None, **kwargs):
        queryset = Report.objects.all()
        serializer = age_serializer.ReportListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, *args, _request=None, _version=None, pk=None, **kwargs):
        try:
            report = Report.objects.get(pk=pk)
        except Report.DoesNotExist:
            return Response(
                {"status": "418", "message": msg["fa"]["report"]["report_not_found"]}
            )
        serializer = age_serializer.ReportListSerializer(report)
        result = {}
        result["status"] = "200"
        result["message"] = msg["fa"]["report"]["report_found"]
        result["data"] = serializer.data
        return Response(result)


class FetchLinks(APIView):
    def get(self, _request, _version):
        return Response({"count": 0, "links": 0})
        # from agency.crawler_engine import CrawlerEngineV2
        # structure_id = request.GET.get("structure_id", None)
        # link = request.GET.get("link", None)
        # if structure_id is None:
        #     raise NotAcceptable(detail="structure_id is not acceptable")
        # if link is None:
        #     raise NotAcceptable(detail="link is not acceptable")
        # structure = get_object_or_404(Structure, pk=structure_id)
        # crawler = CrawlerEngineV2()
        # links = crawler.get_links(structure.news_links_structure, link)
        # return Response({"count": len(links), "links": links})


class FetchContent(APIView):
    def get(self, _request, _version):
        return Response({"content": ""})
        # from agency.crawler_engine import CrawlerEngineV2
        # structure_id = request.GET.get("structure_id", None)
        # link = request.GET.get("link", None)
        # if link is None or structure_id is None:
        #     raise NotAcceptable(detail="link or structure_id is not acceptable")
        # structure = get_object_or_404(Structure, pk=structure_id)
        # crawler = CrawlerEngineV2()
        # content = crawler.get_content(structure.news_meta_structure, link)
        # return Response({"content": content})


class TestErrorView(APIView):
    def get(self, _request, _version):
        logger.error("Exception happened for test purposes!!!")
        raise Exception("Exception happened for test purposes!")
