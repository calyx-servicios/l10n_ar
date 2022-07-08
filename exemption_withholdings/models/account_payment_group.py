from odoo import models, fields


class AccountPaymentGroup(models.Model):
    _inherit = 'account.payment.group'

    exempt_msj = fields.Html('Exemptions Information')