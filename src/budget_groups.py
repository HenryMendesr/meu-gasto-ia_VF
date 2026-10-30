"""Broad planning groups, separate from the detailed categories on expenses.

Existing category limits remain in storage. An explicit group limit overrides
its component category limits for that month, including when it is zero.
"""
from decimal import Decimal, ROUND_HALF_UP
import unicodedata


GROUPS = [
    {
        'id': '@budget:fixed',
        'label': 'Custos fixos',
        'description': 'Moradia, mercado, carro, transporte, saúde e contas.',
        'categories': ['Mercado', 'Transporte', 'Moradia', 'Saúde', 'Contas'],
        'aliases': ['Carro', 'Automóvel', 'Gasolina', 'Combustível', 'Aluguel',
                    'Farmácia', 'Internet', 'Luz', 'Água', 'Custos fixos'],
    },
    {
        'id': '@budget:comfort',
        'label': 'Conforto',
        'description': 'Alimentação fora, compras e assinaturas.',
        'categories': ['Alimentação', 'Compras', 'Assinaturas'],
        'aliases': [],
    },
    {
        'id': '@budget:leisure',
        'label': 'Lazer e experiências',
        'description': 'Lazer, viagens e presentes.',
        'categories': ['Lazer', 'Viagem', 'Presentes'],
        'aliases': [],
    },
    {
        'id': '@budget:learning',
        'label': 'Conhecimento',
        'description': 'Educação, cursos e estudos.',
        'categories': ['Educação'],
        'aliases': ['Cursos'],
    },
    {
        'id': '@budget:other',
        'label': 'Outros',
        'description': 'Outros gastos e categorias personalizadas.',
        'categories': ['Outros'],
        'aliases': [],
    },
]
GROUP_IDS = frozenset(group['id'] for group in GROUPS)
def normalized_category(category: str) -> str:
    """Match category names across case and accent differences."""
    return ''.join(
        char for char in unicodedata.normalize('NFKD', str(category).strip().casefold())
        if not unicodedata.combining(char)
    )


_CATEGORY_GROUPS = {
    normalized_category(category): group['id']
    for group in GROUPS
    for category in group['categories'] + group['aliases']
}


def group_id(category: str) -> str:
    """Resolve detailed categories; unassigned custom categories go to Outros."""
    if category in GROUP_IDS:
        return category
    return _CATEGORY_GROUPS.get(normalized_category(category), '@budget:other')


def effective_limits(raw: dict[str, float]) -> dict[str, float]:
    """Read old and grouped limits without modifying or double-counting either."""
    totals = {group['id']: Decimal(0) for group in GROUPS}
    for category, value in raw.items():
        if category not in GROUP_IDS:
            totals[group_id(category)] += Decimal(str(value))
    return {
        group['id']: float(
            (Decimal(str(raw[group['id']])) if group['id'] in raw else totals[group['id']])
            .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        )
        for group in GROUPS
    }
