import inspect
import time

from django.conf import settings


class _statsd(object):
    def incr(s, *a, **kw):
        pass

    def timing(s, *a, **kw):
        pass


try:
    from statsd import statsd
except ImportError:
    statsd = _statsd()


class FrameOptionsHeader(object):
    """
    Set an X-Frame-Options header. Default to DENY. Set
    response['x-frame-options'] = 'SAMEORIGIN'
    to override.
    """

    def process_response(self, request, response):
        if hasattr(response, 'no_frame_options'):
            return response

        if not 'x-frame-options' in response:
            response['x-frame-options'] = 'DENY'

        return response


class StrictTransportMiddleware(object):
    """
    Set the Strict-Transport-Security header on responses. Use the
    STS_MAX_AGE setting to control the max-age value. (Default: 1 month.)
    Use the STS_SUBDOMAINS boolean to add includeSubdomains.
    (Default: False.)
    """

    def process_response(self, request, response):
        if request.is_secure():
            age = getattr(settings, 'STS_MAX_AGE', 2592000)  # 30 days.
            subdomains = getattr(settings, 'STS_SUBDOMAINS', False)
            val = 'max-age=%d' % age
            if subdomains:
                val += '; includeSubDomains'
            response['Strict-Transport-Security'] = val
        return response


class GraphiteMiddleware(object):

    def process_response(self, request, response):
        statsd.incr('response.%s' % response.status_code)
        if hasattr(request, 'user') and request.user.is_authenticated():
            statsd.incr('response.auth.%s' % response.status_code)
        return response

    def process_exception(self, request, exception):
        statsd.incr('response.500')
        if hasattr(request, 'user') and request.user.is_authenticated():
            statsd.incr('response.auth.500')


class GraphiteRequestTimingMiddleware(object):
    """statsd's timing data per view."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        view = view_func
        if not inspect.isfunction(view_func):
            view = view.__class__
        try:
            request._view_module = view.__module__
            request._view_name = view.__name__
            request._start_time = time.time()
        except AttributeError:
            pass

    def process_response(self, request, response):
        self._record_time(request)
        return response

    def process_exception(self, request, exception):
        self._record_time(request)

    def _record_time(self, request):
        if hasattr(request, '_start_time'):
            ms = int((time.time() - request._start_time) * 1000)
            data = dict(module=request._view_module, name=request._view_name,
                        method=request.method)
            statsd.timing('view.{module}.{name}.{method}'.format(**data), ms)
            statsd.timing('view.{module}.{method}'.format(**data), ms)
            statsd.timing('view.{method}'.format(**data), ms)
