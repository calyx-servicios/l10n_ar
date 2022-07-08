# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = "res.partner"

    line_padron_type_ids = fields.Many2many('account.padron.retention.perception.type', 
                                    'res_partner_padron_type_rel',  'padron_type_id', 'partner_id', 
                                    string="Rel Partner Patterns", copy=False, readonly=False)


    @api.model
    def create(self, values):
        record = super(ResPartner, self).create(values)
        if record.afip_responsability_type_id.code not in ('5', '7', '8', '9') and self.env['ir.config_parameter'].get_param('account_padron_withholding_perception.check_census_on_create'):
            padrones = self.env['account.padron.retention.perception.type'].search([]).ids
            record.write({'line_padron_type_ids': [(6, 0, padrones)]})
        return record

    def write(self, values):
        padron_control={}
        for rec in self:
            for line_obj in rec.line_padron_type_ids:
                padron_control[str(line_obj.id)] = line_obj
            return_var = super(ResPartner, rec).write(values)
            for padron_index in padron_control:
                padron_control[padron_index].partner_control()
            if rec.line_padron_type_ids:
                rec.import_padron_server_partner()

    def import_padron_server_partner(self, context={}):
        partner_dic={} #padron_type_id
        for partner_obj in self:  
            partner_dic[partner_obj.main_id_number] = partner_obj
            context['partner_dic'] = partner_dic
            for padron_obj in partner_obj.line_padron_type_ids:
                result_ids = self.env['account.import.padron.ret.perc'].search([
                                                                ('padron_type_id', '=', padron_obj.id),
                                                                ('state','=', 'open')
                                                                ])
                for import_obj in result_ids:
                    import_obj.import_padron_server(context=context)

