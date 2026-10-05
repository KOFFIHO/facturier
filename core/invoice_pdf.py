# Génère le PDF d'une facture au format A5 (adapté à l'impression sur
# feuille A5 en Côte d'Ivoire), entièrement en français, prix en F CFA.
# Affiche la réduction éventuelle, les articles offerts (cadeaux) et les
# modes de paiement combinés (espèces, Orange Money, MTN Money, Moov Money...).

import io
import os

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas


PAGE_WIDTH, PAGE_HEIGHT = A5  # ~419.5 x 595.3 points (148 x 210 mm)
MARGIN = 24
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


PAYMENT_LABELS = {
    "ESPECES": "Espèces",
    "ORANGE_MONEY": "Orange Money",
    "MTN_MONEY": "MTN Money",
    "MOOV_MONEY": "Moov Money",
    "CARTE": "Carte bancaire",
    "CHEQUE": "Chèque",
    "AUTRE": "Autre",
}


def format_fcfa(amount) -> str:
    """
    Formate un montant en Francs CFA :
    - sans décimales
    - séparateur de milliers par espace
    - suffixe F CFA
    """
    return f"{round(amount):,}".replace(",", " ") + " F CFA"


def _resolve_media_path(image_field):
    """
    Retourne le chemin physique d'un fichier média Django.
    """
    if not image_field:
        return None

    try:
        path = image_field.path
        return path if os.path.exists(path) else None
    except (ValueError, FileNotFoundError):
        return None


def _wrap_text(text, max_width, font_name, font_size):
    """
    Découpe un texte en plusieurs lignes afin qu'il tienne
    dans la largeur maximale disponible.

    Cela évite que les désignations longues soient tronquées.
    """
    text = str(text or "")

    words = text.split(" ")
    lines = []
    current = ""

    for word in words:
        trial = f"{current} {word}".strip()

        if not current or stringWidth(
            trial,
            font_name,
            font_size
        ) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines or [""]


def build_invoice_pdf(sale, config) -> io.BytesIO:
    """
    Construit le PDF de la facture au format A5
    et retourne le fichier PDF en mémoire.
    """

    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A5
    )

    top = PAGE_HEIGHT - MARGIN

    # ==========================================================
    # EN-TÊTE
    # ==========================================================

    # Logo rond à droite
    logo_cx = MARGIN + CONTENT_WIDTH - 22
    logo_cy = top - 16

    c.setLineWidth(1)
    c.circle(
        logo_cx,
        logo_cy,
        20,
        stroke=1,
        fill=0
    )

    logo_path = _resolve_media_path(
        getattr(config, "logo", None)
    )

    if logo_path:
        try:
            c.saveState()

            clip = c.beginPath()
            clip.circle(
                logo_cx,
                logo_cy,
                19
            )

            c.clipPath(
                clip,
                stroke=0,
                fill=0
            )

            c.drawImage(
                logo_path,
                logo_cx - 19,
                logo_cy - 19,
                width=38,
                height=38,
                preserveAspectRatio=True,
                mask="auto",
            )

            c.restoreState()

        except Exception:
            pass

    else:
        c.setFont(
            "Helvetica-Oblique",
            5.5
        )

        c.drawCentredString(
            logo_cx,
            logo_cy + 2,
            "Votre logo"
        )

        c.drawCentredString(
            logo_cx,
            logo_cy - 5,
            "ici"
        )

    # ==========================================================
    # NOM ENTREPRISE + COORDONNÉES
    # ==========================================================

    y = top - 42

    c.setFillColorRGB(
        0.07,
        0.07,
        0.07
    )

    c.setFont(
        "Helvetica-Bold",
        13
    )

    c.drawCentredString(
        PAGE_WIDTH / 2,
        y,
        config.name or "Nom de votre entreprise"
    )

    # Adresse
    y -= 13

    c.setFont(
        "Helvetica",
        7
    )

    c.setFillColorRGB(
        0.25,
        0.25,
        0.25
    )

    c.drawCentredString(
        PAGE_WIDTH / 2,
        y,
        config.address or "Adresse | Ville | Côte d'Ivoire"
    )

    # Site + email
    y -= 9

    site_email = " | ".join(
        filter(
            None,
            [
                config.website,
                config.email
            ]
        )
    ) or "Site web | Email"

    c.drawCentredString(
        PAGE_WIDTH / 2,
        y,
        site_email
    )

    # Téléphone
    y -= 9

    c.drawCentredString(
        PAGE_WIDTH / 2,
        y,
        f"Tél : {config.phone or '00 00 00 00 00'}"
    )

    # ==========================================================
    # NUMÉRO FACTURE / DATE
    # ==========================================================

    y -= 16

    c.setFillColorRGB(
        0,
        0,
        0
    )

    c.setFont(
        "Helvetica-Bold",
        8.5
    )

    c.drawString(
        MARGIN,
        y,
        "N° Facture :"
    )

    c.setFont(
        "Helvetica",
        8.5
    )

    c.drawString(
        MARGIN + 62,
        y,
        sale.invoice_code
    )

    c.setFont(
        "Helvetica-Bold",
        8.5
    )

    c.drawString(
        MARGIN + CONTENT_WIDTH - 110,
        y,
        "Date :"
    )

    c.setFont(
        "Helvetica",
        8.5
    )

    c.drawString(
        MARGIN + CONTENT_WIDTH - 80,
        y,
        sale.created_at.strftime("%d/%m/%Y")
    )

    # Vendeur
    y -= 12

    c.setFont(
        "Helvetica-Bold",
        8.5
    )

    c.drawString(
        MARGIN,
        y,
        "Vendeur :"
    )

    c.setFont(
        "Helvetica",
        8.5
    )

    c.drawString(
        MARGIN + 50,
        y,
        sale.seller_name or "—"
    )

    # ==========================================================
    # BLOC CLIENT
    # ==========================================================

    y -= 16

    c.setFont(
        "Helvetica-Bold",
        8.5
    )

    c.drawString(
        MARGIN,
        y,
        "CLIENT"
    )

    y -= 12

    box_h = 26

    c.setLineWidth(1)

    c.rect(
        MARGIN,
        y - box_h,
        CONTENT_WIDTH,
        box_h,
        stroke=1,
        fill=0
    )

    # Nom
    c.setFont(
        "Helvetica-Bold",
        7.5
    )

    c.drawString(
        MARGIN + 6,
        y - 10,
        "Nom :"
    )

    c.setFont(
        "Helvetica",
        7.5
    )

    c.drawString(
        MARGIN + 34,
        y - 10,
        sale.client_name or "Client comptoir"
    )

    # Téléphone
    c.setFont(
        "Helvetica-Bold",
        7.5
    )

    c.drawString(
        MARGIN + 6,
        y - 21,
        "Téléphone :"
    )

    c.setFont(
        "Helvetica",
        7.5
    )

    c.drawString(
        MARGIN + 55,
        y - 21,
        sale.client_phone or "-"
    )

    # ==========================================================
    # TABLEAU DES ARTICLES
    # ==========================================================

    y = y - box_h - 12

    col_qty = MARGIN
    col_desc = MARGIN + 30
    col_price = MARGIN + CONTENT_WIDTH - 130
    col_amount = MARGIN + CONTENT_WIDTH - 65

    row_h = 14

    # En-tête du tableau
    c.setFillColorRGB(
        0.07,
        0.07,
        0.07
    )

    c.rect(
        MARGIN,
        y - 16,
        CONTENT_WIDTH,
        16,
        stroke=0,
        fill=1
    )

    c.setFillColorRGB(
        1,
        1,
        1
    )

    c.setFont(
        "Helvetica-Bold",
        7.5
    )

    c.drawString(
        col_qty + 4,
        y - 11,
        "QTÉ"
    )

    c.drawString(
        col_desc + 4,
        y - 11,
        "DÉSIGNATION"
    )

    c.drawString(
        col_price + 4,
        y - 11,
        "P.U."
    )

    c.drawString(
        col_amount + 4,
        y - 11,
        "MONTANT"
    )

    c.setFillColorRGB(
        0,
        0,
        0
    )

    y -= 16

    items = list(
        sale.items.all()
    )

    table_top = y

    desc_max_width = (
        col_price - col_desc - 8
    )

    line_height = 8.5

    # ==========================================================
    # LIGNES DES ARTICLES
    # ==========================================================

    for item in items:

        label = item.designation

        if item.is_gift:
            label += " (OFFERT)"

        desc_lines = _wrap_text(
            label,
            desc_max_width,
            "Helvetica",
            7.5
        )

        montant = (
            0
            if item.is_gift
            else max(
                0,
                item.price * item.quantity
                - item.discount_amount
            )
        )

        amount_lines = [
            f"{round(montant):,}".replace(
                ",",
                " "
            )
        ]

        if item.discount_amount > 0:
            amount_lines.append(
                f"(-{round(item.discount_amount):,} F CFA)"
                .replace(",", " ")
            )

        row_h = max(
            14,
            max(
                len(desc_lines),
                len(amount_lines)
            ) * line_height + 5
        )

        row_y = y - row_h

        text_top_y = (
            row_y
            + row_h
            - 9
        )

        # Bordure de ligne
        c.setStrokeColorRGB(
            0.82,
            0.82,
            0.82
        )

        c.setLineWidth(
            0.5
        )

        c.rect(
            MARGIN,
            row_y,
            CONTENT_WIDTH,
            row_h,
            stroke=1,
            fill=0
        )

        # Texte
        c.setFillColorRGB(
            0,
            0,
            0
        )

        c.setFont(
            "Helvetica",
            7.5
        )

        # Quantité
        c.drawString(
            col_qty + 4,
            text_top_y,
            str(item.quantity)
        )

        # Prix unitaire
        c.drawString(
            col_price + 4,
            text_top_y,
            (
                "0"
                if item.is_gift
                else f"{round(item.price):,}".replace(
                    ",",
                    " "
                )
            )
        )

        # Désignation
        for i, line in enumerate(desc_lines):

            c.drawString(
                col_desc + 4,
                text_top_y - (
                    i * line_height
                ),
                line
            )

        # Montant
        for i, line in enumerate(amount_lines):

            if i > 0:
                c.setFillColorRGB(
                    0.7,
                    0.1,
                    0.1
                )

                c.setFont(
                    "Helvetica",
                    6.5
                )

            c.drawString(
                col_amount + 4,
                text_top_y - (
                    i * line_height
                ),
                line
            )

            if i > 0:

                c.setFillColorRGB(
                    0,
                    0,
                    0
                )

                c.setFont(
                    "Helvetica",
                    7.5
                )

        y = row_y

    # Lignes verticales du tableau
    for x in [
        col_qty,
        col_desc,
        col_price,
        col_amount,
        MARGIN + CONTENT_WIDTH
    ]:

        c.setStrokeColorRGB(
            0.82,
            0.82,
            0.82
        )

        c.line(
            x,
            table_top,
            x,
            y
        )

    # ==========================================================
    # TOTAUX
    # ==========================================================
    #
    # 
    # Les libellés sont à gauche et les montants
    # sont parfaitement alignés à droite.
    # ==========================================================

    y -= 14

    totals_left = MARGIN
    totals_right = MARGIN + CONTENT_WIDTH

    # ----------------------------------------------------------
    # Sous-total
    # ----------------------------------------------------------

    c.setFillColorRGB(
        0.0,
        0.0,
        0.0
    )

    c.setFont(
        "Helvetica",
        8
    )

    c.drawString(
        totals_left,
        y,
        "Sous-total"
    )

    c.drawRightString(
        totals_right,
        y,
        format_fcfa(
            sale.sub_total
        )
    )

    # ----------------------------------------------------------
    # Réduction
    # ----------------------------------------------------------

    if (
        sale.discount_amount
        and sale.discount_amount > 0
    ):

        y -= 12

        label = "Réduction"

        if sale.discount_type == "PERCENTAGE":
            label += (
                f" ({sale.discount_value:g}%)"
            )

        c.setFillColorRGB(
            0.7,
            0.1,
            0.1
        )

        c.drawString(
            totals_left,
            y,
            label
        )

        c.drawRightString(
            totals_right,
            y,
            f"- {format_fcfa(sale.discount_amount)}"
        )

    # ----------------------------------------------------------
    # TVA
    # ----------------------------------------------------------

    y -= 12

    c.setFillColorRGB(
        0.0,
        0.0,
        0.0
    )

    c.drawString(
        totals_left,
        y,
        f"TVA ({config.tva_rate:g}%)"
    )

    c.drawRightString(
        totals_right,
        y,
        format_fcfa(
            sale.tva_amount
        )
    )

    # ----------------------------------------------------------
    # Ligne de séparation
    # ----------------------------------------------------------

    y -= 10

    c.setStrokeColorRGB(
        0.75,
        0.75,
        0.75
    )

    c.setLineWidth(
        0.6
    )

    c.line(
        totals_left,
        y + 4,
        totals_right,
        y + 4
    )

    # ----------------------------------------------------------
    # TOTAL
    # ----------------------------------------------------------

    y -= 2

    c.setFillColorRGB(
        0,
        0,
        0
    )

    c.setFont(
        "Helvetica-Bold",
        10
    )

    c.drawString(
        totals_left,
        y,
        "Total"
    )

    c.drawRightString(
        totals_right,
        y,
        format_fcfa(
            sale.total
        )
    )

    # ==========================================================
    # MODES DE PAIEMENT UTILISÉS
    # ==========================================================

    y -= 24

    c.setFont(
        "Helvetica-Bold",
        7.5
    )

    c.drawString(
        MARGIN,
        y,
        "RÈGLEMENT :"
    )

    c.setFont(
        "Helvetica",
        7.5
    )

    payments_text = "   /   ".join(
        f"{PAYMENT_LABELS.get(p.method, p.method)} : "
        f"{format_fcfa(p.amount)}"
        for p in sale.payments.all()
    )

    c.drawString(
        MARGIN + 62,
        y,
        payments_text[:70]
    )

    # ==========================================================
    # SIGNATURE / CACHET
    # ==========================================================

    y -= 20

    box_h2 = 52

    c.setFont(
        "Helvetica-Bold",
        7.5
    )

    c.drawString(
        MARGIN,
        y,
        "Signature / Cachet :"
    )

    c.setLineWidth(
        1
    )

    c.rect(
        MARGIN,
        y - box_h2 - 4,
        CONTENT_WIDTH,
        box_h2,
        stroke=1,
        fill=0
    )

    stamp_path = _resolve_media_path(
        getattr(config, "stamp", None)
    )

    if stamp_path:

        try:

            padding = 5

            c.drawImage(
                stamp_path,
                MARGIN + padding,
                y - box_h2 - 4 + padding,
                width=CONTENT_WIDTH - 2 * padding,
                height=box_h2 - 2 * padding,
                preserveAspectRatio=True,
                mask="auto",
            )

        except Exception:
            pass

    # ==========================================================
    # NOTES
    # ==========================================================

    y = (
        y
        - box_h2
        - 4
        - 14
    )

    c.setFont(
        "Helvetica-Bold",
        7.5
    )

    c.drawString(
        MARGIN,
        y,
        "Notes :"
    )

    c.setLineWidth(
        0.6
    )

    c.line(
        MARGIN + 34,
        y - 2,
        MARGIN + CONTENT_WIDTH,
        y - 2
    )

    if sale.notes:

        c.setFont(
            "Helvetica",
            7.5
        )

        c.drawString(
            MARGIN + 34,
            y,
            sale.notes[:55]
        )

    # ==========================================================
    # PIED DE PAGE
    # ==========================================================

    c.setFont(
        "Helvetica-Oblique",
        8.5
    )

    c.setFillColorRGB(
        0.07,
        0.07,
        0.07
    )

    c.drawCentredString(
        PAGE_WIDTH / 2,
        MARGIN,
        "Merci pour votre confiance !"
    )

    # ==========================================================
    # FINALISATION DU PDF
    # ==========================================================

    c.showPage()
    c.save()

    buffer.seek(0)

    return buffer
