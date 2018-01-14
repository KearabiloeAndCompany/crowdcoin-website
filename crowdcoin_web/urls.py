"""crowdcoin_web URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin
from www.views import *
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views import static
from django.conf import settings

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^verify/(?P<voucher_code>.*)/$', StatusView.as_view(), name='status'),
    url(r'^static/(?P<path>.*)$', static.serve, {'document_root': settings.STATIC_ROOT}),
    url(r'^payfast/', include('payfast.urls')),
    url(r'^pay/redirect', pay_with_payfast, name='pay_with_payfast'),        
    url(r'^process/', process_crowdcoin_payment, name='process_crowdcoin_payment'), 
    url(r'^$', LandingView.as_view(), name='landing'),
]+ staticfiles_urlpatterns()
