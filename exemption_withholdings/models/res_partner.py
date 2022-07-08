from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    exemption_withholding_ids = fields.One2many('exemption.withholding', 'partner_id', string='Exemption Withholding', required=True)