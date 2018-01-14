from django.shortcuts import render, redirect
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.generic import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.template import RequestContext, loader
from django.conf import settings
from django.contrib import messages
from payfast.forms import PayFastForm
from django.views.decorators.csrf import csrf_exempt
import requests
import json
import urllib
import logging
logger = logging.getLogger(__name__)
from freshdesk.api import API as FreshdeskApi

# Create your views here.

def custom_404(request):
    context_variables={}
    template = loader.get_template('404.html')
    next = request.META.get('HTTP_REFERER', None) or '/'
    context_variables['next']=next
    context= RequestContext(request,context_variables)
    return HttpResponse(template.render(context))

def custom_500(request):
    context_variables={}
    template = loader.get_template('500.html')
    next = request.META.get('HTTP_REFERER', None) or '/'
    context_variables['next']=next
    context= RequestContext(request,context_variables)
    return HttpResponse(template.render(context))


def freshdesk_new_ticket(name,subject, description, email=None, phone=None,priority=1, status=2,source=2):
    freshdesk_api = FreshdeskApi(settings.FRESHDESK_URL, settings.FRESHDESK_KEY, version=2)
    try:
        # SMS Alert
        #TODO: Send sms to Freshdesk ticket admin via api
        try:
            amount = json.loads(description).get('amount')
        except Exception as e:
            amount = None

        message="{subject}\nR{amount}\n{phone}\n{name}\n".format(subject=subject,phone=phone,name=name, amount=amount)
        api_response = requests.post(settings.CROWDCOIN_API_URL+'sms_outbound/',
            data={'msisdn':settings.CROWDCOIN_ADMIN_MSISDN,'message':message},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
        logger.info(api_response.reason)

        ticket = freshdesk_api.tickets.create_ticket(subject,
            description=description,
            email=email,
            phone=phone,
            name=name,
            type='Lead',
            responder_id=6003130775,
            priority=priority)

    except Exception as e:
        logger.warning(e.message)
    return

class LandingView(View):
    context ={}

    def get(self, request, *args, **kwargs):
        template_name = "landing.html"
        logger.info("GET")
        logger.info(request.session.get('current_purchase'))
        api_response = requests.get(settings.CROWDCOIN_API_URL+'merchants/?display_on_website=1',auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
        logger.info(api_response.reason)
        self.context['merchants'] = api_response.json()['objects']
        self.context['active_nav'] = 'Home'
        request.session['lite_version'] = bool(request.GET.get('lite',False))
        return render(request, template_name, self.context)

    def post(self, request, *args, **kwargs):
        template_name = "landing.html"
        if not request.session.get('current_purchase'):
            request.session['current_purchase'] = {}
        current_purchase = request.session.get('current_purchase')
        self.context['active_nav'] = 'Home'
        data = {}

        self.context['previous'] = request.META.get('HTTP_REFERER', None) or '/'
        current_purchase['screen'] = request.POST.get('screen')
        logger.info('Screen: ')
        logger.info(current_purchase['screen'] )


        if current_purchase['screen'] == 'swap_form_landing':
            current_purchase['pocket_from'] = 'default'
            current_purchase['amount'] = float(request.POST.get('voucher_amount',0))-5
            current_purchase['recipient_msisdn'] = request.POST.get('voucher_msisdn','0')
            current_purchase['recipient_name'] = request.POST.get('recipient_name')
            current_purchase['sender_name'] = request.POST.get('voucher_product')
            current_purchase['status'] = 'Pending'
            current_purchase['product'] = request.POST.get('voucher_product')
            logger.info('Product: ')
            logger.info(current_purchase['product'] )

            if current_purchase['product'] == 'None':
                response = "Please select a product."
                messages.add_message(request, messages.INFO,response)
                template_name = "landing.html"

            elif current_purchase['amount'] == '' or int(current_purchase['amount']) < 2:
                response = "Please enter an amount between 2 and 1000."
                messages.add_message(request, messages.INFO,response)
                template_name = "landing.html"
            else:
                try:
                    description = json.dumps(current_purchase)
                    logger.info(description)
                    logger.info(len(description))
                    freshdesk_new_ticket(
                        name=current_purchase['recipient_name'],
                        description=description,
                        phone=current_purchase['recipient_msisdn'],
                        subject="NEW MERCHANT PAYMENT LEAD - {product}".format(product=current_purchase['product'])
                    )
                except Exception as e:
                    logger.info(e.message)           

                api_response = redirect('/process/', data=data).json()   

                #Create OTP request
                api_response = requests.post(
                    settings.CROWDCOIN_API_URL+'otp/',
                    data={'msisdn':current_purchase['recipient_msisdn']},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD)).json()
                logger.info(api_response)

                if api_response.get('status') == 'success' and  current_purchase['product'] not in ['', 'None', None]:
                    template_name = "verify-otp.html"
                else:
                    response = api_response.get('message')
                    messages.add_message(request, messages.INFO,response)
                    template_name = "landing.html"

        elif current_purchase['screen'] == 'swap_form_verify_otp':
            current_purchase['otp'] = request.POST.get('otp')

            # Verify OTP
            api_response = requests.get(
                settings.CROWDCOIN_API_URL+'otp/',
                params={'msisdn':current_purchase['recipient_msisdn'],'otp':current_purchase['otp']},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD)).json()
            logger.info(api_response)

            if not api_response.get('status') == 'success':
                template_name = "verify-otp.html"
                response = api_response.get('message')
                messages.add_message(request, messages.INFO,response)
            else:
                response = api_response.get('message')
                messages.add_message(request, messages.INFO,response)
                if current_purchase['product'] in ['Absa Cash Send','Standard Bank Instant Money','MTN Airtime']:
                    template_name = "voucher-details.html"

                if current_purchase['product'] in ['Vodacom','MTN']:
                    #ToDo: Log to freshdesk
                    template_name = "airtime-transfer-details.html"
                    current_purchase['screen'] = 'swap_airtime_transfer_details'
                    api_response = requests.get(
                        settings.CROWDCOIN_API_URL+'deposit_lead/',
                        params={'network':current_purchase['product'],'amount':current_purchase['amount']+5},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
                    logger.info(api_response.reason)
                    api_response = api_response.json()
                    logger.info(api_response)
                    if api_response.get('status') == 'success':
                        deposit_lead = api_response.get('response')
                        response = "Complete your purchase by manually transferring R {amount} Airtime to {transfer_msisdn}.".format(amount=deposit_lead.get('amount'),
                            transfer_msisdn=deposit_lead.get('msisdn'),instructions=deposit_lead.get('instructions'))
                    else:
                        response = api_response.get('response')
                    messages.add_message(request, messages.INFO,response)
                    self.context['airtime_transfer_response'] = api_response

                elif current_purchase['product'] == 'Crowdcoin Voucher':                  
                    return redirect('/pay/redirect/?amount={amount}&product={product}-{recipient}'.format(amount=current_purchase['amount'],product=current_purchase['product'], recipient=current_purchase['recipient_msisdn']))

        elif current_purchase['screen'] == 'swap_form_voucher_details':
            current_purchase['sender_msisdn'] = 'Code:{code}-Pin:{pin}'.format(code=request.POST.get('voucher_code'),pin=request.POST.get('voucher_pin'))

            api_response = requests.post(
                settings.CROWDCOIN_API_URL+'voucher_payments/',
                data=current_purchase,auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
            logger.info(api_response.reason)
            api_response = api_response.json()
            current_purchase['crowdcoin_voucher'] = api_response.get('resource_uri')

            try:
                if api_response.get('status'):
                    voucher = api_response
                    logger.warning(voucher)
                    request.session['current_purchase'] = {}
                    response = "R{amount} Voucher sucessfully sent to {recipient_msisdn}".format(amount=voucher.get('amount'),recipient_msisdn=voucher.get('recipient_msisdn'))
                    messages.add_message(request, messages.INFO,response)
                    return redirect('/verify/'+voucher.get('voucher_code'))
                elif api_response.get('error'):
                    response = api_response.get('error')['message']
                else:
                    response = "An unknown error occured. Our engineering team has been notified about this."
                messages.add_message(request, messages.INFO,response)
            except Exception as e:
                response = e.message
                logger.warning(e.message)
                messages.add_message(request, messages.INFO,response)


        elif current_purchase['screen'] == 'swap_airtime_transfer_details':
            current_purchase['sender_msisdn'] = 'Code:{code}-Pin:{pin}'.format(code=request.POST.get('voucher_code'),pin=request.POST.get('voucher_pin'))
            #Get Airtime Transfer Number
            api_response = requests.get(
                settings.CROWDCOIN_API_URL+'deposit_lead/',
                params={'network':'Vodacom','amount':current_purchase['amount']+5},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
            logger.info(api_response.reason)
            api_response = api_response.json()
            logger.info(api_response)
            tranfer_details = api_response


            api_response = requests.post(
                settings.CROWDCOIN_API_URL+'voucher_payments/',
                data=current_purchase,auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
            logger.info(api_response.reason)
            api_response = api_response.json()
            current_purchase['crowdcoin_voucher'] = api_response.get('resource_uri')

            try:
                if api_response.get('status'):
                    voucher = api_response
                    logger.warning(voucher)
                    request.session['current_purchase'] = {}
                    response = "R{amount} Voucher sucessfully sent to {recipient_msisdn}".format(amount=voucher.get('amount'),recipient_msisdn=voucher.get('recipient_msisdn'))
                    messages.add_message(request, messages.INFO,response)
                    return redirect('/verify/'+voucher.get('voucher_code'))
                elif api_response.get('error'):
                    response = api_response.get('error')['message']
                else:
                    response = "An unknown error occured. Our engineering team has been notified about this."
                messages.add_message(request, messages.INFO,response)
            except Exception as e:
                response = e.message
                logger.warning(e.message)
                messages.add_message(request, messages.INFO,response)                

        return render(request, template_name, self.context)        


class StatusView(View):
    template_name = "status.html"
    context = []
    def get(self, request, *args, **kwargs):
        voucher_code = kwargs.get('voucher_code')
        logger.info(voucher_code)
        api_response = requests.get(settings.CROWDCOIN_API_URL+'voucher_payments/?voucher_code={voucher_code}'.format(voucher_code=voucher_code),auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
        try:
            voucher = api_response.json()['objects'][0]
            logger.info(voucher)
            voucher['fee'] = voucher.get('fee',5)
            voucher['total'] = voucher.get('amount')+voucher['fee']
        except Exception as e:
            logger.warning(e.message)
            voucher = None
        self.context ={}
        self.context['active_nav'] = 'Pricing'
        self.context['voucher'] = voucher
        request.session['lite_version'] = bool(request.GET.get('lite',False))
        return render(request, self.template_name, self.context)


class PayFastCancelView(View):
    template_name = "payfast/cancel.html"


    def get(self, request, *args, **kwargs):
        context ={}
        return render(request, self.template_name, context)



class PayFastReturnView(View):
    template_name = "payfast/return.html"


    def get(self, request, *args, **kwargs):
        context ={}
        return render(request, self.template_name, context)


def pay_with_payfast(request,*args, **kwargs):
    context ={}
    # Order model have to be defined by user, it is not a part
    # of django-payfast
    amount = request.GET.get('amount')
    item_name = request.GET.get('product')

    form = PayFastForm(initial={
        # required params:
        'amount':amount,
        'item_name': item_name,
        'return_url' : request.scheme +"://"+ request.get_host()+'/payfast/return/',
        'cancel_url' : request.scheme +"://"+ request.get_host()+'/payfast/cancel/',
        'notify_url' : request.scheme +"://"+ request.get_host()+'/payfast/notify/'
    })
    context['form'] = form
    context['previous'] = request.META.get('HTTP_REFERER', None) or '/'
    context['amount'] = amount
    context['product'] = item_name
    return render(request, 'payfast/pay.html', context)    


def create_crowdcoin_payment(self, request, *args, **kwargs):
    context ={}
    crowdcoin_api = requests
    profile = crowdcoin_api.get(settings.CROWDCOIN_API_URL+'profile/').json()
    context['profile'] = profile
    data=request.POST.copy()
    data['reference'] = account=data.get('account_no')
    api_response = crowdcoin_api.post(settings.CROWDCOIN_API_URL+'crowdcoin_payments/', data=data).json()
    logger.info(api_response)
    if not api_response.get('error') or not api_response.get('error_message'):
        response = "Your payment was successful. Please allow upto 48 hours for the transaction to reflect in the recivieng institution's account."
    else:
        response = api_response.get('error',api_response.get('error_message'))
    messages.add_message(request, messages.INFO,response)
    request.session['active_side_pane'] = 'Payments'
    return render(request, self.template_name, context)


@csrf_exempt
def process_crowdcoin_payment( request, *args, **kwargs):
    try:
        template_name = "process.html"
        context ={}
        if request.method == 'POST':
        	posted_data = request.POST.copy()
        else:
        	posted_data = request.GET.copy()
        
        logger.info(posted_data)
        if  posted_data.get('merchant_id'):
            api_response = requests.get(settings.CROWDCOIN_API_URL+'profile/', headers={'Authorization':'ApiKey %s:%s'%(posted_data.get('merchant_id'),posted_data.get('merchant_key'))})
            profile = api_response.json()
            pocket_to = profile['default_pocket']['resource_uri']
            api_response = requests.get(settings.CROWDCOIN_API_URL+'merchants/?display_on_website=1',params={'default_pocket__tag':profile['default_pocket']['tag']},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
            merchant = api_response.json()['objects'][0]

        else:
            api_response = requests.get(settings.CROWDCOIN_API_URL+'merchants/?display_on_website=1',params={'default_pocket__tag':posted_data.get('pocket_to')},auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
            merchant = api_response.json()['objects'][0]
            profile =merchant['profile']
            pocket_to = profile['default_pocket']['resource_uri']



        headers = {'Content-Type': 'application/json'}
        data = {
            'username':profile['user']['username'],
            'api_key':profile['user']['key'],
            'amount':posted_data.get('amount'),
            'reference': posted_data.get('reference',posted_data.get('m_payment_id')),
            'pocket_to':  pocket_to,
            'item_name': posted_data.get('item_name'),
            'item_description': posted_data.get('item_description'),
            'return_url': posted_data.get('return_url','/'),
            'notify_url': posted_data.get('notify_url','/'),
            'cancel_url': posted_data.get('cancel_url','/')
        }

        logger.info(data)
        context['transaction'] = []

        #Check if transaction exists
        api_response = requests.get(settings.CROWDCOIN_API_URL+'crowdcoin_payments/', params={'reference':data.get('reference')} ,  headers=headers, auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD)).json()
        if api_response['meta']['total_count'] == 0:

            # Create Crowdcoin Payment Transaction
            airtime_deposit = requests.post(settings.CROWDCOIN_API_URL+'airtime_deposits/', json={"amount":posted_data.get('amount'),"network":"Vodacom",'pocket':  pocket_to}, headers=headers, auth=(settings.CROWDCOIN_DEFAULT_USER, settings.CROWDCOIN_DEFAULT_PASSWORD))
            if airtime_deposit.status_code in [200, 201] and airtime_deposit.json().get('resource_uri'):
                airtime_deposit_lead = airtime_deposit.json()
                
                #TODO: Handle unfound Sim card

                data['airtime_deposit_lead'] = airtime_deposit_lead.get('resource_uri')
                api_response = requests.post(settings.CROWDCOIN_API_URL+'crowdcoin_payments/?username={username}&api_key={api_key}'.format(username=data.get('username'),api_key=data.get('api_key')), json=data, headers=headers)

                if api_response.status_code in [200, 201]:
                    context['transaction'] = api_response.json()
            else:
                message = "We could not assign a payment number for this payment. Please try again."
                messages.add_message(request, messages.INFO,message)
                return redirect('/')

        else:
            context['transaction'] = api_response['objects'][0]

        context['profile'] = profile
        context['merchant'] = merchant
    except Exception,e:
        logger.exception(e)
    return render(request, template_name, context)

