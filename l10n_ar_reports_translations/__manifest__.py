# pylint: disable=missing-module-docstring,pointless-statement
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Argentina Reports Translations",
    "summary": """
        Translations for IngAdhoc Argentina reports
    """,
    "author": "Calyx Servicios S.A.",
    "maintainers": ["marcooegg"],
    "website": "https://odoo.calyx-cloud.com.ar/",
    "license": "AGPL-3",
    "category": "Localization/Argentina",
    "version": "13.0.1.0.0",
    "development_status": "Production/Stable",
    "application": False,
    "installable": True,
    "auto_install": True,
    "post_init_hook": "post_init_hook",
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": ["base", "l10n_ar_reports"],
}
