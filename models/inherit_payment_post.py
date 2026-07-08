import requests
from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.model_create_multi
    def create(self, vals_list):
        # 1. Create standard Odoo payment records
        payments = super(AccountPayment, self).create(vals_list)

        # 2. After creation, push to E-Tax API
        for payment in payments:
            if payment.payment_type == 'inbound': # Only post incoming customer payments
                payment._post_payment_to_etaxris()
                
        return payments

    def _post_payment_to_etaxris(self):
        self.ensure_one()
        
        buyer_tin = self.partner_id.vat or "Unknown TIN"
        invoice_no = self.ref or self.name or "Unknown Invoice"
        payment_date = self.date
        
        # Calculate 10% VAT
        sales_amount = float(self.amount)
        vat_amount = sales_amount * 0.10
        payment_method = self.payment_method_id.name or "payment"

        payload = {
            'buyer_tin': buyer_tin,
            'invoice_no': invoice_no,
            'payment_date': str(payment_date),
            'sales_amount': sales_amount,
            'vat_amount': vat_amount,
            'payment_method': payment_method
        }

        payment_url = "http://localhost:8069/api/etax/payment"
        token = "ac71b0212d793d832e7b1c742c007a88bc01d6ecce320a34324108a32d16b352"
        
        # Include token in payload as requested
        payload['token'] = token

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            request_payload = {"params": payload}
            
            response = requests.post(payment_url, json=request_payload, headers=headers, timeout=5)
            data = response.json().get('result', {})
            
            if data.get('status') != 'success':
                error_msg = _("E-Tax API Error: %s") % str(data.get('message', 'Unknown error'))
                _logger.error(error_msg)
                self.message_post(body=error_msg)
                return False

            success_msg = _("Successfully posted payment for %s to E-Tax System.") % invoice_no
            self.message_post(body=success_msg)
            return True

        except requests.exceptions.RequestException as e:
            error_msg = _("E-Tax Network Error: %s") % str(e)
            _logger.error(error_msg)
            self.message_post(body=error_msg)
            return False
