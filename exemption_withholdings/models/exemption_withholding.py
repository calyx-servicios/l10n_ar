from odoo import models, fields, _


class ExemptionWithholdings(models.Model):
    _name = 'exemption.withholding'
    _description = _("Exemption Withholdings")

    partner_id = fields.Many2one('res.partner', string='Partner',required=True)
    date_from = fields.Datetime('Date from', required=True)
    date_to = fields.Datetime('Date to', required=True)
    account_tax_id = fields.Many2one('account.tax', string='Withholding', domain=[('type_tax_use', '=', 'supplier')], required=True)
    active_tax = fields.Boolean('Active', default=True)