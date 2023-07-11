# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, fields, api, _

class AccountPadronRetentionPerceptionLine(models.Model):
    _name = 'account.padron.retention.perception.line'
    _description = _("Account patterns withholding and perception line")

    import_padron_id = fields.Many2one('account.import.padron.ret.perc', string="Import Header", ondelete='cascade')
    padron_type_id = fields.Many2one('account.padron.retention.perception.type',  string='Type Padron', ondelete='cascade')
    arba_alicuot_id = fields.Many2one('res.partner.arba_alicuot', string="Perception Related", ondelete='cascade')
    in_padron = fields.Boolean(default=True)
    cuit = fields.Char(string='CUIT')
    partner_id = fields.Many2one('res.partner', string="Partner")
    date_from = fields.Date('Date From')
    date_to = fields.Date('Date To')
    percentage_retention = fields.Float(string='Percentage Retention')
    percentage_perception = fields.Float(string='Percentage Perception')


    def calcule_retention(self,amount_base,payment_group_obj,base_discount):
        # Calcular las retenciones
        for self_obj in self:
            currency_id = payment_group_obj.currency_id.with_context(date=payment_group_obj.payment_date)
            amount_base = currency_id.compute(amount_base, payment_group_obj.company_id.currency_id)
            amount_return = 0.0
            if self_obj.padron_type_id:
                if amount_base >= self_obj.padron_type_id.minimum_base_retention:
                    amount_return = amount_base / 100.0 * self_obj.percentage_retention
                if amount_return < self_obj.padron_type_id.minimum_calcule_retention:
                    amount_return = 0.0
                if base_discount != 0.0:
                    base_discount = currency_id.compute(base_discount, payment_group_obj.company_id.currency_id)
                    amount_return = (amount_base-base_discount) / 100.0 * self_obj.percentage_retention
            return amount_return

    def create_arba_perception_line(self):
        # Crear las percepciones
        for self_obj in self:
            vals = {
                'tag_id': self_obj.padron_type_id.account_tag_perception_id.id ,
                'from_date': self_obj.date_from ,
                'to_date': self_obj.date_to ,
                'alicuota_percepcion': self_obj.percentage_perception,
                'alicuota_retencion': self_obj.percentage_retention,
                'partner_id': self_obj.partner_id.id,
                'padron_line_id': self_obj.id,
            }
            if not self_obj.arba_alicuot_id:

                arba_alicuot = self.env['res.partner.arba_alicuot'].create(vals)
                self_obj.write({'arba_alicuot_id': arba_alicuot.id})
            else:
                self_obj.arba_alicuot_id.write(vals)
