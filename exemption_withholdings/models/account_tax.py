from odoo import models, fields
from datetime import datetime


class AccountTax(models.Model):
    _inherit = 'account.tax'


    def create_payment_withholdings(self, payment_group):
        tax_exempt = self.env['account.tax']
        for rec in self:
            for exempt_id in payment_group.partner_id.exemption_withholding_ids:
                if exempt_id.active_tax and exempt_id.account_tax_id in rec and \
                exempt_id.date_from < datetime.today() and\
                exempt_id.date_to > datetime.today():
                    tax_exempt += exempt_id.account_tax_id
                else:
                    continue
            rec = rec - tax_exempt
            if len(tax_exempt) > 0:
                exempt_msj = ''
                for tax in tax_exempt:
                    if len(exempt_msj) > 0:
                        exempt_msj += ', '
                    exempt_msj += tax.name
                exempt_msj += '.'
                payment_group.write({'exempt_msj':  exempt_msj})

        return super(AccountTax, self).create_payment_withholdings(payment_group)
