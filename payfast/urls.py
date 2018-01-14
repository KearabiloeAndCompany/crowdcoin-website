from django.conf.urls import url, include
from payfast.views import notify_handler
from www.views import PayFastCancelView,PayFastReturnView

urlpatterns = [
    url('^notify/$', notify_handler, name='payfast_notify'),
    url('^cancel/$', PayFastCancelView.as_view(), name='payfast_cancel'),
    url('^return/$', PayFastReturnView.as_view(), name='payfast_return')
]
