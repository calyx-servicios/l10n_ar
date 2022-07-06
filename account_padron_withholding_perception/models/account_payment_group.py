# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentGroup(models.Model):
    _inherit = "account.payment.group"

    def compute_withholdings(self):
        self.ensure_one()
        result = super(AccountPaymentGroup, self).compute_withholdings()
        if self:
            # Facturas de compras
            list_amount_tag_retention = {}
            list_amount_tag_retention_discount = {}
            # aca recorre las lineas de las facturas
            # para poder buscar en cada linea si corresponde o no cobrar
            for move_line_obj in self.debt_move_line_ids:
                if (
                    move_line_obj.invoice_id
                    and move_line_obj.invoice_id.type
                    in ("in_invoice", "in_refund")
                ):
                    percentage2use_invoice = (
                        move_line_obj.invoice_id.residual
                        / move_line_obj.invoice_id.amount_total
                    )
                    list_amount_tag_retention = self.search_list_amount_tag_retention(
                        list_amount_tag_retention,
                        percentage2use_invoice,
                        move_line_obj,
                    )
                if not move_line_obj.invoice_id:
                    if move_line_obj.debit != 0.0:
                        # aca ver como poner para cuando paga una
                        # factura con un debito(pago anterior) mas grande
                        percentage2use = 1
                        list_amount_tag_retention_discount = self.search_all_tag_retention(
                            list_amount_tag_retention_discount,
                            percentage2use,
                            move_line_obj,
                        )

            if self.selected_debt != 0.0:
                percentage2use_payment = (self.to_pay_amount / self.selected_debt)
                # esta pregunta si al menos possee una linea para calcular
                for tag_retention_id in list_amount_tag_retention:
                    amount2use = (
                        list_amount_tag_retention[tag_retention_id]
                        * percentage2use_payment
                    )
                    base_discount = 0.0
                    if tag_retention_id in list_amount_tag_retention_discount:
                        base_discount = list_amount_tag_retention_discount[
                            tag_retention_id
                        ]
                    self.env[
                        "account.padron.retention.perception.type"
                    ].create_retention(
                        tag_retention_id, amount2use, self, base_discount
                    )
            # aca procesa todos los padrones que tiene
            # relacionado el partner cuando el pago es sin facturas
            if not self.debt_move_line_ids:
                base_discount = 0.0
                for padron_line_obj in self.partner_id.line_padron_type_ids:
                    self.env[
                        "account.padron.retention.perception.type"
                    ].create_retention(
                        padron_line_obj.id,
                        self.to_pay_amount,
                        self,
                        base_discount,
                    )
        self.change_currency_payments()
        return result

    def search_all_tag_retention(self, list_amount_tag_retention_discount, percentage2use, move_line_obj):
        for rec in self:
            currency_id = rec.payment_currency_id.with_context(date=rec.payment_date)
            for padron_obj in move_line_obj.partner_id.line_padron_type_ids:
                for tag_obj in move_line_obj.tax_ids:
                    if padron_obj.account_tax_retention_id.id == tag_obj.id:
                        amount2use = move_line_obj.debit
                        if rec.currency_id.id != rec.payment_currency_id.id:
                            amount2use = currency_id.compute(move_line_obj.amount_currency, rec.currency_id)
                        if (not str(padron_obj.id) in list_amount_tag_retention_discount):
                            list_amount_tag_retention_discount[str(padron_obj.id)] = (amount2use * percentage2use)
                        else:
                            list_amount_tag_retention_discount[str(padron_obj.id)] += (amount2use * percentage2use)
        return list_amount_tag_retention_discount

    def search_list_amount_tag_retention(self, list_amount_tag_retention, percentage2use_invoice, move_line_obj):
        for rec in self:
            obj_move = move_line_obj.invoice_id.journal_document_type_id
            for invoice_line_obj in move_line_obj.invoice_id.invoice_line_ids:
                currency_id = move_line_obj.currency_id.with_context(date=rec.payment_date)  # para usar el valor del dolar del pago
                for tag_obj in invoice_line_obj.ret_perc_type_ids:
                    amount2use = (invoice_line_obj.quantity * invoice_line_obj.price_unit)
                    amount2use = currency_id.compute(amount2use, rec.currency_id)
                    if obj_move.document_type_id.internal_type in ("invoice", "debit_note",):
                        if not str(tag_obj.id) in list_amount_tag_retention:
                            list_amount_tag_retention[str(tag_obj.id)] = (
                                amount2use * percentage2use_invoice)
                        else:
                            list_amount_tag_retention[str(tag_obj.id)] += (
                                amount2use * percentage2use_invoice)
    
                    if obj_move.document_type_id.internal_type == "credit_note":
                        if not str(tag_obj.id) in list_amount_tag_retention:
                            list_amount_tag_retention[str(tag_obj.id)] = (
                                amount2use * (-1) * percentage2use_invoice)
                        else:
                            list_amount_tag_retention[str(tag_obj.id)] -= (
                                amount2use * percentage2use_invoice)
        return list_amount_tag_retention

