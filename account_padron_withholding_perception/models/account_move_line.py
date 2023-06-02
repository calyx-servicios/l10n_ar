# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    ret_perc_type_ids = fields.Many2many('account.padron.retention.perception.type', 
                                'rel_invoice_line_padron_type',  
                                'invoice_line_id', 
                                'padron_type_id', string="Padron Type", readonly=0)
    
    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.move_id.partner_id and self.move_id.move_type in ('in_invoice','in_refund'): # Factura proveedor
            list_add =  []
            for line_obj in self.move_id.partner_id.line_padron_type_ids:
                list_add.append(line_obj.id)
            self.ret_perc_type_ids = list_add 

