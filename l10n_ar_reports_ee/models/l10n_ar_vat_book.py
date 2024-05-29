# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, api, models
from odoo.exceptions import UserError
from collections import OrderedDict
from odoo.tools.misc import format_date
import re
import json
import zipfile
import io


class L10nARVatBook(models.AbstractModel):

    _name = "l10n_ar.vat.book"
    _inherit = "account.report"
    _description = "Argentinian VAT Book"

    filter_date = {'date_from': '', 'date_to': '', 'filter': 'this_month'}
    filter_all_entries = False
    filter_product_category = True

    def print_pdf(self, options):
        options.update({
            'journal_type': self.env.context.get('journal_type')
        })
        return super(L10nARVatBook, self).print_pdf(options)

    def print_xlsx(self, options):
        options.update({
            'journal_type': self.env.context.get('journal_type')
        })
        return super(L10nARVatBook, self).print_xlsx(options)

    @api.model
    def _get_options_domain(self, options):
        # OVERRIDE
        domain = super(L10nARVatBook, self)._get_options_domain(options)
        # Filter accounts based on the search bar.
        product_category_ids = options.get('product_category_ids', [])
        if options.get('filter_all_entries'):
            domain += [
                '|',
                ('account_id.name', 'ilike', options['filter_accounts']),
                ('account_id.code', 'ilike', options['filter_accounts'])
            ]
        for tuple in domain:
            if 'product_id.categ_id' in tuple:
                domain.remove(tuple)
                break
        return domain, product_category_ids
    
    @api.model
    def _get_dynamic_columns(self, options):
        """ Show or not the VAT 2.5% and VAT 5% columns if this ones are active/inactive """
        res = []
        if self.env['account.tax'].search([('type_tax_use', '=', options.get('journal_type')), ('tax_group_id.l10n_ar_vat_afip_code', '=', '9')]):
            res.append({'sql_var': 'vat_25', 'name': _('VAT 2,5%')})
        if self.env['account.tax'].search([('type_tax_use', '=', options.get('journal_type')), ('tax_group_id.l10n_ar_vat_afip_code', '=', '8')]):
            res.append({'sql_var': 'vat_5', 'name': _('VAT 5%')})
        return res

    def _get_columns_name(self, options):
        dynamic_columns = [item.get('name') for item in self._get_dynamic_columns(options)]
        return [
            {'name': _("Date"), 'class': 'date'},
            {'name': _("Document"), 'class': 'text-left'},
            {'name': _("Name"), 'class': 'text-left'},
            {'name': _("Vat Cond."), 'class': 'text-left'},
            {'name': _("VAT"), 'class': 'text-left'},
            {'name': _('Taxed'), 'class': 'number'},
            {'name': _('Not Taxed'), 'class': 'number'},
        ] + [{'name': item, 'class': 'number'} for item in dynamic_columns] + [
            {'name': _('VAT 10,5%'), 'class': 'number'},
            {'name': _('VAT 21%'), 'class': 'number'},
            {'name': _('VAT 27%'), 'class': 'number'},
            {'name': _('VAT Perc'), 'class': 'number'},
            {'name': _('Other Taxes'), 'class': 'number'},
            {'name': _('Total'), 'class': 'number'},
        ]

    def total_less(self, total_less={}, tax_amounts=[]):
        if not total_less:
            total_less = {
                'taxed': 0.0,
                'not_taxed': 0.0,
                'vat_25': 0.0,
                'vat_5': 0.0,
                'vat_10': 0.0,
                'vat_21': 0.0,
                'vat_27': 0.0,
                'vat_per': 0.0,
                'other_taxes': 0.0,
                'total': 0.0,
            }
        if tax_amounts:
            for tax in tax_amounts:
                tax_id = tax['id']
                tax_value = self.env['account.tax'].browse(tax_id).amount
                tax_amount =tax['amount']
                tax_base = tax['base']

                if tax_value == 21.0:
                    total_less['vat_21'] += tax_amount
                elif tax_value == 27.0:
                    total_less['vat_27'] += tax_amount
                elif tax_value == 2.5:
                    total_less['vat_25'] += tax_amount
                elif tax_value == 5.0:
                    total_less['vat_5'] += tax_amount
                elif tax_value == 10.5:
                    total_less['vat_10'] += tax_amount
                else:
                    total_less['other_taxes'] += tax_amount
            total_less['taxed'] += tax_base
            if total_less['total'] != 0.0:
                total_less['total'] = 0.0
        return total_less
    
    def decimal(self, value):
        str_value = str(value)
        str_decimals = str_value.find('.')
        two_decimals_int = int(value * 100)
        two_decimals_float = two_decimals_int / 100

        if str_decimals == -1:
            len_decimals = 0
        else:
            len_decimals = len(str_value[str_decimals + 1:])
        
        if len_decimals < 3:
            return two_decimals_float
        else:
            try:
                third_decimal = int(str_value[str_decimals + 3])
            except:
                third_decimal = 0

            if third_decimal >= 5:
                two_decimals_float += 0.01

            return two_decimals_float
    
    @api.model
    def _get_lines(self, options, line_id=None):        
        journal_type = options.get('journal_type')
        if not journal_type:
            journal_type = self.env.context.get('journal_type', 'sale')
            options.update({'journal_type': journal_type})
        lines = []
        line_id = 0
        sign = 1.0 if journal_type == 'purchase' else -1.0
        domain = self._get_lines_domain(options)
        options_domain, category_filter = self._get_options_domain (options=options)
        domain += options_domain
        dynamic_columns = [item.get('sql_var') for item in self._get_dynamic_columns(options)]
        totals = {}.fromkeys(['taxed', 'not_taxed'] + dynamic_columns + ['vat_10', 'vat_21', 'vat_27', 'vat_per', 'other_taxes', 'total'], 0)
        total_less = {}
        changes = False
        search_read = self.env['account.ar.vat.line'].search_read(domain)

        for rec in search_read:            
            total_less = {}
            len_invoice_line_ids = len(rec['invoice_line_ids'])
            if len_invoice_line_ids > 0:
                for line_id in rec['invoice_line_ids']:
                    invoice_line = self.env['account.move.line'].browse(line_id)
                    taxes = invoice_line.tax_ids.filtered(lambda tax: tax.type_tax_use == 'sale') if journal_type == 'sale' else invoice_line.tax_ids.filtered(lambda tax: tax.type_tax_use == 'purchase')
                    
                    tax_amount = taxes.compute_all(
                        invoice_line.price_unit,
                        invoice_line.currency_id,
                        invoice_line.quantity,
                        product=invoice_line.product_id,
                        partner=self.env['res.partner'].browse(rec['partner_id'][0])
                    )
                    if category_filter: 
                        if invoice_line.product_id.categ_id.id not in category_filter:
                            total_less = self.total_less(total_less, tax_amount['taxes'])
                            len_invoice_line_ids -= 1
                        else:
                            tax_amount = []
                            total_less = self.total_less(total_less=total_less)
                    else:
                        tax_amount = []
                        total_less = self.total_less(total_less=total_less)
                if len_invoice_line_ids > 0:
                    less_vat_10 = - self.decimal(total_less['vat_10']) if journal_type == 'sale' else self.decimal(total_less['vat_10'])
                    less_vat_21 = - self.decimal(total_less['vat_21']) if journal_type == 'sale' else self.decimal(total_less['vat_21'])
                    #less_vat_25 = - self.decimal(total_less['vat_25']) if journal_type == 'sale' else self.decimal(total_less['vat_25'])
                    #less_vat_5 = - self.decimal(total_less['vat_5']) if journal_type == 'sale' else self.decimal(total_less['vat_5'])
                    less_vat_21 = - self.decimal(total_less['vat_21']) if journal_type == 'sale' else self.decimal(total_less['vat_21'])
                    less_vat_27 = - self.decimal(total_less['vat_27']) if journal_type == 'sale' else self.decimal(total_less['vat_27'])
                    less_vat_per = - self.decimal(total_less['vat_per']) if journal_type == 'sale' else self.decimal(total_less['vat_per'])
                    less_taxed = - self.decimal(total_less['taxed']) if journal_type == 'sale' else self.decimal(total_less['taxed'])
                    less_not_taxed = - self.decimal(total_less['not_taxed']) if journal_type == 'sale' else self.decimal(total_less['not_taxed'])
                    less_other_taxes = - self.decimal(total_less['other_taxes']) if journal_type == 'sale' else self.decimal(total_less['other_taxes'])
                    #less_total = - self.decimal(total_less['total']) if journal_type == 'sale' else self.decimal(total_less['total'])

                    taxed = rec['base_25'] + rec['base_5'] + rec['base_10'] + rec['base_21'] + rec['base_27']
                    other_taxes = rec['other_taxes']
                    if rec['type'] in ['in_invoice', 'in_refund']:
                        caret_type = 'account.invoice.in'
                    elif rec['type'] in ['out_invoice', 'out_refund']:
                        caret_type = 'account.invoice.out'
                    else:
                        caret_type = 'account.move'

                    if len_invoice_line_ids != len(rec['invoice_line_ids']):
                        if max(abs(other_taxes * sign), abs(less_other_taxes)) != 0 and abs(other_taxes * sign + less_other_taxes) / max(abs(other_taxes * sign ), abs(less_other_taxes)) <= 0.01:
                            oth_taxes = sign * - self.decimal(other_taxes) if journal_type == 'sale' else self.decimal(other_taxes)
                        else:
                            oth_taxes = - less_other_taxes if journal_type == 'sale' else less_other_taxes
                        changes = True
                    else:
                        changes = False
                    append_taxed = sign * (taxed) if not changes else (sign * (self.decimal(taxed - less_taxed)) if less_taxed != 0 else sign * taxed)
                    append_not_taxed =  sign * rec['not_taxed'] if not changes else (sign * (rec['not_taxed']) if less_not_taxed != 0 else sign * rec['not_taxed'])
                    append_vat_10 = sign * rec['vat_10'] if not changes else (sign * (self.decimal(rec['vat_10'] - less_vat_10)) if less_vat_10 != 0 else sign * rec['vat_10'])
                    append_vat_21 = sign * rec['vat_21'] if not changes else (sign * (self.decimal(rec['vat_21'] - less_vat_21)) if less_vat_21 != 0 else sign * rec['vat_21'])
                    append_vat_27 = sign * rec['vat_27'] if not changes else (sign * (self.decimal(rec['vat_27'] - less_vat_27)) if less_vat_27 != 0 else sign * rec['vat_27'])
                    append_vat_per = sign * rec['vat_per'] if not changes else (sign * (rec['vat_per']) if less_vat_per != 0 else rec['vat_per'])                        
                    append_other_taxes = sign * rec['other_taxes'] if not changes else (sign * (self.decimal(other_taxes - oth_taxes)) if less_other_taxes != 0 else sign * other_taxes)                    
                    less_total = self.decimal(append_taxed + append_not_taxed + append_vat_10 + append_vat_21 + append_vat_27+ append_vat_per + append_other_taxes)
                    less_total = - less_total if journal_type == 'sale' else less_total
                    append_total = sign * rec['total'] if not changes else sign * (less_total)
                    totals['taxed'] += append_taxed
                    totals['not_taxed'] += rec['not_taxed']

                    for item in dynamic_columns:
                        totals[item] += rec[item]
                    totals['vat_10'] += append_vat_10
                    totals['vat_21'] += append_vat_21

                    totals['vat_27'] += append_vat_27
                    totals['vat_per'] += rec['vat_per']
                    totals['other_taxes'] += append_other_taxes
                    totals['total'] += append_total
                    
                    lines.append({
                        'id': rec['id'],
                        'name': format_date(self.env, rec['invoice_date']),
                        'class': 'date' + (' text-muted' if rec['state'] != 'posted' else ''),
                        'level': 2,
                        'model': 'account.ar.vat.line',
                        'caret_options': caret_type,
                        'columns': [
                            {'name': rec['move_name']},
                            {'name': rec['partner_name']},
                            {'name': rec['afip_responsibility_type_name']},
                            {'name': rec['cuit']},
                            {'name': self.format_value(append_taxed)},
                            {'name': self.format_value(append_not_taxed)},
                            ] + [
                                {'name': self.format_value(sign * rec[item])} for item in dynamic_columns] + [
                            {'name': self.format_value(append_vat_10)},
                            {'name': self.format_value(append_vat_21)},
                            {'name': self.format_value(append_vat_27)},
                            {'name': self.format_value(append_vat_per)},
                            {'name': self.format_value(append_other_taxes)},
                            {'name': self.format_value(append_total)},
                        ],
                    })
                    line_id += 1
        totals['total'] = totals['taxed'] + totals['not_taxed'] + totals['vat_10'] + totals['vat_21'] + totals['vat_27'] + totals['vat_per'] + totals['other_taxes']
        lines.append({
            'id': 'total',
            'name': _('Total'),
            'class': 'o_account_reports_domain_total',
            'level': 0,
            'columns': [
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': self.format_value(totals['taxed'])},
                {'name': self.format_value(totals['not_taxed'])},
                ] + [
                    {'name': self.format_value(totals[item])} for item in dynamic_columns] + [
                {'name': self.format_value(totals['vat_10'])},
                {'name': self.format_value(totals['vat_21'])},
                {'name': self.format_value(totals['vat_27'])},
                {'name': self.format_value(totals['vat_per'])},
                {'name': self.format_value(totals['other_taxes'])},
                {'name': self.format_value(totals['total'])},
            ],
        })

        return lines

    def get_report_filename(self, options):
        """ Return the name that will be used for the file when downloading pdf, xlsx, txt_file, etc """
        journal_type = options.get('journal_type')
        filename = {'sale': 'Libro_IVA_Ventas', 'purchase': 'Libro_IVA_Compras'}.get(journal_type, 'Libro_IVA')
        return "%s_%s" % (filename, options['date']['date_to'])

    def _get_reports_buttons(self):
        """ Add buttons to print the txt files used for AFIP to report the vat books """
        buttons = super(L10nARVatBook, self)._get_reports_buttons()
        buttons += [{'name': _('VAT Book (ZIP)'), 'sequence': 3, 'action': 'export_vat_book_files', 'file_export_type': _('ZIP')}]
        return buttons

    def export_vat_book_files(self, options):
        """ Button that lets us export the VAT book zip which contains the files that we upload to AFIP for Purchase VAT Book """
        options.update({'journal_type': self.env.context.get('journal_type', 'sale')})
        return {
            'type': 'ir_actions_account_report_download',
            'data': {'model': self.env.context.get('model'),
                     'options': json.dumps(options),
                     'output_format': 'zip',
                     'financial_id': self.env.context.get('id')
                     }
        }

    def _get_txt_files(self, options):
        """ Compute the date to be printed in the txt files"""
        lines = []
        aliquots = self._get_REGINFO_CV_ALICUOTAS(options)
        for k, v in aliquots.items():
            lines += v
        aliquots_data = '\r\n'.join(lines).encode('ISO-8859-1')
        vouchers_data = '\r\n'.join(self._get_REGINFO_CV_CBTE(options, aliquots)).encode('ISO-8859-1')
        return vouchers_data, aliquots_data

    def get_zip(self, options):
        txt_types = ['purchases', 'goods_import', 'used_goods'] if options.get('journal_type') == 'purchase' else ['sale']
        filenames = {
            'purchases': 'Compras',
            'purchases_aliquots': 'IVA_Compras',
            'goods_import': 'Importaciones_de_Bienes',
            'goods_import_aliquots': 'IVA_Importaciones_de_Bienes',
            'used_goods': 'Compras_Bienes_Usados',
            'used_goods_aliquots': 'IVA_Compras_Bienes_Usados',
            'sale': 'Ventas',
            'sale_aliquots': 'IVA_Ventas'
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for txt_type in txt_types:
                options.update({'txt_type': txt_type})
                vouchers_data, aliquots_data = self._get_txt_files(options)
                if vouchers_data:
                    zf.writestr(filenames.get(txt_type) + '.txt', vouchers_data)
                if aliquots_data:
                    zf.writestr(filenames.get('%s_aliquots' % txt_type) + '.txt', aliquots_data)
        return stream.getvalue()

    @api.model
    def _get_lines_domain(self, options):
        company_ids = self.env.company.ids
        domain = [('journal_id.type', '=', options.get('journal_type')),
                  ('journal_id.l10n_latam_use_documents', '=', True), ('company_id', 'in', company_ids)]
        state = options.get('all_entries') and 'all' or 'posted'
        if state and state.lower() != 'all':
            domain += [('state', '=', state)]
        if options.get('date').get('date_to'):
            domain += [('date', '<=', options['date']['date_to'])]
        if options.get('date').get('date_from'):
            domain += [('date', '>=', options['date']['date_from'])]
        return domain

    @api.model
    def _format_amount(self, amount, padding=15, decimals=2):
        """ We need to represent float numbers as  integers, with certain padding and taking into account certain
        decimals to ba take into account. For example:

            amount -2.1589 with default padding and decimales
            should return -00000000000215 which is:
               * a integer with padding 15 that includes the sign of the amount if negative
               * the integer part of the amount concatenate with 2 digits of the decimal part of the amount """
        template = "{:0" + str(padding) + "d}"
        return template.format(round(amount * 10**decimals))

    @api.model
    def _get_partner_document_code_and_number(self, partner):
        """ For a given partner turn the identification coda and identification number in the expected format for the
        txt files """
        # CUIT is mandatory for all except for final consummer
        if partner.l10n_ar_afip_responsibility_type_id.code == '5':
            doc_code = "{:0>2d}".format(int(partner.l10n_latam_identification_type_id.l10n_ar_afip_code))
            doc_number = partner.vat or ''
            # we clean the letters that are not supported
            doc_number = re.sub("[^0-9]", "", doc_number)
        elif partner.l10n_ar_afip_responsibility_type_id.code == '9':
            commercial_partner = partner.commercial_partner_id
            doc_number = partner.l10n_ar_vat or (commercial_partner.country_id.l10n_ar_legal_entity_vat \
                if commercial_partner.is_company else commercial_partner.country_id.l10n_ar_natural_vat)
            doc_code = '80'
        else:
            doc_number = partner.ensure_vat()
            doc_code = '80'
        return doc_code, doc_number.rjust(20, '0')

    @api.model
    def _get_pos_and_invoice_invoice_number(self, invoice):
        res = invoice._l10n_ar_get_document_number_parts(
            invoice.l10n_latam_document_number, invoice.l10n_latam_document_type_id.code)
        return "{:0>20d}".format(res['invoice_number']), "{:0>5d}".format(res['point_of_sale'])

    def _get_txt_invoices(self, options):
        state = options.get('all_entries') and 'all' or 'posted'
        if state != 'posted':
            raise UserError(_('Can only generate TXT files using posted entries.'
                              ' Please remove Include unposted entries filter and try again'))

        domain = [('l10n_latam_document_type_id.code', '!=', False)] + self._get_lines_domain(options)
        txt_type = options.get('txt_type')
        if txt_type == 'purchases':
            domain += [('l10n_latam_document_type_id.code', 'not in', ['66', '30', '32'])]
        elif txt_type == 'goods_import':
            domain += [('l10n_latam_document_type_id.code', '=', '66')]
        elif txt_type == 'used_goods':
            domain += [('l10n_latam_document_type_id.code', 'in', ['30', '32'])]
        return self.env['account.move'].search(domain, order='invoice_date asc, name asc, id asc')

    def _get_tax_row(self, invoice, base, code, tax_amount, options):
        inv = invoice
        journal_type = options.get('journal_type')
        impo = options.get('txt_type') == 'goods_import'

        invoice_number, pos_number = self._get_pos_and_invoice_invoice_number(inv)
        doc_code, doc_number = self._get_partner_document_code_and_number(inv.commercial_partner_id)
        if journal_type == 'sale':
            row = [
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),  # Field 1: Tipo de Comprobante
                pos_number,  # Field 2: Punto de Venta
                invoice_number,  # Field 3: Número de Comprobante
                self._format_amount(base),  # Field 4: Importe Neto Gravado
                str(code).rjust(4, '0'),  # Field 5: Alícuota de IVA.
                self._format_amount(tax_amount),  # Field 6: Impuesto Liquidado.
            ]
        elif impo:
            row = [
                (inv.l10n_latam_document_number or inv.name or '').rjust(16, '0'),  # Field 1: Despacho de importación.
                self._format_amount(base),  # Field 2: Importe Neto Gravado
                str(code).rjust(4, '0'),  # Field 3: Alícuota de IVA
                self._format_amount(tax_amount),  # Field 4: Impuesto Liquidado.
            ]
        else:
            row = [
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),  # Field 1: Tipo de Comprobante
                pos_number,  # Field 2: Punto de Venta
                invoice_number,  # Field 3: Número de Comprobante
                doc_code,  # Field 4: Código de documento del vendedor
                doc_number,  # Field 5: Número de identificación del vendedor
                self._format_amount(base),  # Field 6: Importe Neto Gravado
                str(code).rjust(4, '0'),  # Field 7: Alícuota de IVA.
                self._format_amount(tax_amount),  # Field 8: Impuesto Liquidado.
            ]
        return row

    def _get_REGINFO_CV_CBTE(self, options, aliquots):
        res = []
        journal_type = options.get('journal_type')
        invoices = self._get_txt_invoices(options)

        for inv in invoices:
            aliquots_count = len(aliquots.get(inv))

            currency_rate = inv.l10n_ar_currency_rate
            currency_code = inv.currency_id.l10n_ar_afip_code

            invoice_number, pos_number = self._get_pos_and_invoice_invoice_number(inv)
            doc_code, doc_number = self._get_partner_document_code_and_number(inv.partner_id)

            amounts = inv._l10n_ar_get_amounts()
            vat_amount = amounts['vat_amount']
            vat_exempt_base_amount = amounts['vat_exempt_base_amount']
            vat_untaxed_base_amount = amounts['vat_untaxed_base_amount']
            other_taxes_amount = amounts['other_taxes_amount']
            vat_perc_amount = amounts['vat_perc_amount']
            iibb_perc_amount = amounts['iibb_perc_amount']
            mun_perc_amount = amounts['mun_perc_amount']
            intern_tax_amount = amounts['intern_tax_amount']
            perc_imp_nacionales_amount = amounts['profits_perc_amount'] + amounts['other_perc_amount']

            if vat_exempt_base_amount:
                if inv.partner_id.l10n_ar_afip_responsibility_type_id.code == '10':  # free zone operation
                    operation_code = 'Z'
                elif inv.l10n_latam_document_type_id.l10n_ar_letter == 'E':          # exportation operation
                    operation_code = 'X'
                else:                                                                # exempt operation
                    operation_code = 'E'
            elif inv.l10n_latam_document_type_id.code == '66':                       # import clearance
                operation_code = 'E'
            elif vat_untaxed_base_amount:                                            # not taxed operation
                operation_code = 'N'
            else:
                operation_code = ' '

            row = [
                inv.invoice_date.strftime('%Y%m%d'),  # Field 1: Fecha de comprobante
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),  # Field 2: Tipo de Comprobante.
                pos_number,  # Field 3: Punto de Venta
                invoice_number,  # Field 4: Número de Comprobante
                # If it is a multiple-sheet receipt, the document number of the first sheet must be reported, taking into account the provisions of article 23, paragraph a), point 6. of General Resolution No. 1,415, the related resolutions that modify and complement this one.
                # In the case of registering grouped by daily totals, the first voucher number of the range to be considered must be entered.
            ]

            if journal_type == 'sale':
                # Field 5: Número de Comprobante Hasta: En el resto de los casos se consignará el dato registrado en el campo 4
                row.append(invoice_number)
            else:
                # Field 5: Despacho de importación
                if inv.l10n_latam_document_type_id.code == '66':
                    row.append((inv.l10n_latam_document_number).rjust(16, '0'))
                else:
                    row.append(''.rjust(16, ' '))
            row += [
                doc_code,  # Field 6: Código de documento del comprador.
                doc_number,  # Field 7: Número de Identificación del comprador
                inv.commercial_partner_id.name.ljust(30, ' ')[:30],  # Field 8: Apellido y Nombre del comprador.
                self._format_amount(inv.amount_total),  # Field 9: Importe Total de la Operación.
                self._format_amount(vat_untaxed_base_amount),  # Field 10: Importe total de conceptos que no integran el precio neto gravado
            ]

            if journal_type == 'sale':
                row += [
                    self._format_amount(0.0),  # Field 11: Percepción a no categorizados
                    # the "uncategorized / responsible not registered" figure is not used anymore
                    self._format_amount(vat_exempt_base_amount),  # Field 12: Importe de operaciones exentas
                    self._format_amount(perc_imp_nacionales_amount + vat_perc_amount),  # Field 13: Importe de percepciones o pagos a cuenta de impuestos Nacionales
                ]
            else:
                row += [
                    self._format_amount(vat_exempt_base_amount),  # Field 11: Importe de operaciones exentas
                    self._format_amount(vat_perc_amount),  # Field 12: Importe de percepciones o pagos a cuenta del Impuesto al Valor Agregado
                    self._format_amount(perc_imp_nacionales_amount),  # Field 13: Importe de percepciones o pagos a cuenta otros impuestos nacionales
                ]

            row += [
                self._format_amount(iibb_perc_amount),  # Field 14: Importe de percepciones de ingresos brutos
                self._format_amount(mun_perc_amount),  # Field 15: Importe de percepciones de impuestos municipales
                self._format_amount(intern_tax_amount),  # Field 16: Importe de impuestos internos
                str(currency_code),  # Field 17: Código de Moneda

                self._format_amount(currency_rate, padding=10, decimals=6),  # Field 18: Tipo de Cambio
                # new modality of currency_rate

                str(aliquots_count),  # Field 19: Cantidad de alícuotas de IVA
                operation_code,  # Field 20: Código de operación.
            ]

            if journal_type == 'sale':
                document_codes = [
                    '16', '19', '20', '21', '22', '23', '24', '27', '28', '29', '33', '34', '35', '37', '38', '43', '44',
                    '45', '46', '47', '48', '49', '54', '55', '56', '57', '58', '59', '60', '61', '68', '81', '82', '83',
                    '110', '111', '112', '113', '114', '115', '116', '117', '118', '119', '120', '150', '151', '157',
                    '158', '159', '160', '161', '162', '163', '164', '165', '166', '167', '168', '169', '170', '171',
                    '172', '180', '182', '183', '185', '186', '188', '189', '190', '191',
                    '201', '202', '203', '206', '207', '208', '211', '212', '213', '331', '332']
                row += [
                    # Field 21: Otros Tributos
                    self._format_amount(other_taxes_amount),

                    # Field 22: vencimiento comprobante
                    # NOTE: it does not appear in instructions but it does in application. for ticket and export invoice is not reported, also for some others but that we do not have implemented
                    inv.l10n_latam_document_type_id.code in document_codes and '00000000' or inv.invoice_date_due.strftime('%Y%m%d')
                ]
            else:
                row.append(self._format_amount(vat_amount))  # Field 21: Crédito Fiscal Computable

                liquido_type = inv.l10n_latam_document_type_id.code in ['033', '058', '059', '060', '063']
                row += [
                    self._format_amount(other_taxes_amount),  # Field 22: Otros Tributos

                    # NOTE: still not implemented on this three fields for use case with third pary commisioner

                    # Field 23: CUIT Emisor / Corredor
                    # It will be reported only if the field 'Tipo de Comprobante' contains '033', '058', '059', '060' or '063'. if there is no intervention of third party in the operation then the informant VAT number will be reported. For the rest of the vouchers it will be completed with zeros
                    self._format_amount(liquido_type and inv.company_id.partner_id.ensure_vat() or 0, padding=11),

                    (liquido_type and inv.company_id.name or '').ljust(30, ' ')[:30],  # Field 24: Denominación Emisor / Corredor

                    # Field 25: IVA Comisión
                    # If field 23 is different from zero, then we will add the VAT tax base amount of thecommission
                    self._format_amount(0),
                ]
            res.append(''.join(row))
        return res

    def _get_REGINFO_CV_ALICUOTAS(self, options):
        """ We return a dict to calculate the number of aliquots when we make the vouchers """
        res = OrderedDict()
        # only vat taxes with codes 3, 4, 5, 6, 8, 9. this follows what is mentioned in http://contadoresenred.com/regimen-de-informacion-de-compras-y-ventas-rg-3685-como-cargar-la-informacion/. We start counting codes 1 (not taxed) and 2 (exempt) if there are no aliquots, we add one of this with 0, 0, 0 in details. we also use mapped in case there are duplicate afip codes (eg manual and auto)
        invoices = self._get_txt_invoices(options)

        for inv in invoices:
            lines = []
            vat_taxes = inv._get_vat()

            # tipically this is for invoices with zero amount
            if not vat_taxes and any(
                    t.tax_group_id.l10n_ar_vat_afip_code and t.tax_group_id.l10n_ar_vat_afip_code != '0'
                    for t in inv.invoice_line_ids.mapped('tax_ids')):
                lines.append(''.join(self._get_tax_row(inv, 0.0, 3, 0.0, options)))

            # we group by afip_code
            for vat_tax in vat_taxes:
                lines.append(''.join(self._get_tax_row(inv, vat_tax['BaseImp'], vat_tax['Id'], vat_tax['Importe'], options)))

            res[inv] = lines

        return res
