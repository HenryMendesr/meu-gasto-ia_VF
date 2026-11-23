"""Reorders each panel so its main numbers and charts come first.

Secondary material (guides, day summaries, histories) moves behind native
disclosures. Elements keep their IDs, so the panel scripts work unchanged.
"""
import re


def take_element(source, marker, start_at=0):
    """Return (element_html, source_without_element) for the first marker match."""
    start = source.index(marker, start_at)
    tag = re.match(r'<([a-z]+)', source[start:])[1]
    depth = 0
    for match in re.finditer(r'</?' + tag + r'\b[^>]*>', source[start:]):
        depth += -1 if match.group().startswith('</') else 1
        if depth == 0:
            end = start + match.end()
            return source[start:end], source[:start] + source[end:]
    raise ValueError('Unclosed element: ' + marker)


def disclosure(label, body, opened=False):
    state = ' open' if opened else ''
    return f'<details class="calm-disclosure"{state}><summary>{label}</summary>{body}</details>'


def reorder(container, markers):
    """Pull the listed children out of a container and put them first, in order."""
    opening = container[:container.index('>') + 1]
    closing = container[container.rindex('</'):]
    inner = container[len(opening):-len(closing)]
    picked = []
    for marker in markers:
        block, inner = take_element(inner, marker)
        picked.append(block)
    return opening + ''.join(picked) + inner + closing


def replace_element(html, marker, transform):
    block, _ = take_element(html, marker)
    return html.replace(block, transform(block), 1)


def investments(html):
    def shell(block):
        banner, block = take_element(block, '<section class="education-banner"')
        guide = re.search(r'<button id="openInvestorGuide"[^>]*>.*?</button>', banner).group()
        simulator = re.search(r'<button id="openInvestmentSimulator"[^>]*>.*?</button>', banner).group()
        simulator = simulator.replace('class="save"', 'class="secondary"').replace(' ↗', '')
        block = block.replace('<div class="actions"><button id="refreshInvestments"',
                              '<div class="actions">' + guide + simulator + '<button id="refreshInvestments"', 1)
        # The banner copy is still updated by investor_education.js; keep it, hidden.
        block = block.replace('<div class="investment-toolbar', '<p id="educationBannerText" hidden></p><div class="investment-toolbar', 1)
        daily, block = take_element(block, '<section class="daily-summary"')
        profile, block = take_element(block, '<section class="suitability-card"')
        block = block.replace('<details class="calm-disclosure"><summary>Gráficos da carteira</summary>',
                              '<details class="calm-disclosure portfolio-charts" open><summary>Gráficos da carteira</summary>', 1)
        block = reorder(block, ['<div class="investment-toolbar', '<section class="investment-summary"',
                                '<div id="investmentCalculationNotice"', '<details class="calm-disclosure portfolio-charts"',
                                '<section class="table-card investment-table"', '<section class="investment-cash"'])
        closing = block.rindex('</section>')
        extras = disclosure('Movimentações do dia', daily) + disclosure('Meu perfil de investidor', profile)
        return block[:closing] + extras + block[closing:]
    html = replace_element(html, '<section class="portfolio-shell">', shell)
    return replace_element(html, '<section class="investment-activity card">',
                           lambda block: disclosure('Histórico de operações', block))


def panel(html, panel_id, markers):
    opening = re.search(r'<(?:div|section) id="' + panel_id + r'"[^>]*>', html).group()
    return replace_element(html, opening, lambda block: reorder(block, markers))


def apply(html):
    html = investments(html)
    # Registrar: the form first; report and list after it.
    html = panel(html, 'entryPanel', ['<header class="section-heading entry-heading">',
                                      '<section class="card statement-upload"', '<section id="statementReview"',
                                      '<section class="card entry"'])
    # Dívidas: totals and charts first; reminders after the contracts.
    html = panel(html, 'debtsPanel', ['<header class="section-heading">', '<section class="debt-totals"',
                                      '<div id="debtPaidSummary"', '<div id="debtStatusMessage"',
                                      '<div class="debt-layout">', '<section class="debt-contracts">',
                                      '<section class="credit-card-section', '<section class="card-bills"'])
    # Ganhos e fixos: summary, then the two editors, then the extras.
    html = panel(html, 'routinePanel', ['<header class="section-heading routine-heading">',
                                        '<div class="routine-summary"', '<section class="card routine-section" id="routineIncome">',
                                        '<section class="card routine-section" id="routineFixed">',
                                        '<section class="card trust-card" id="dailyTasks">'])
    return html
