"""Educational investor profile; methodology and question set versioned together."""
import json
from pathlib import Path

QUESTIONS = json.loads(Path(__file__).with_name('suitability_questions.json').read_text(encoding='utf-8'))
VERSION = 1


def evaluate(payload):
    if not isinstance(payload, dict) or payload.get('version') != VERSION:
        raise ValueError('Versão do questionário inválida. Atualize a página.')
    answers = payload.get('answers')
    if not isinstance(answers, dict) or set(answers) != {q['id'] for q in QUESTIONS}:
        raise ValueError('Responda todas as perguntas para calcular seu perfil.')
    totals = {key: [] for key in ('capacity', 'knowledge', 'tolerance')}
    for q in QUESTIONS:
        value = answers[q['id']]
        if type(value) is not int or not 0 <= value < len(q['options']):
            raise ValueError('Resposta inválida: ' + q['title'])
        dimension = q['dimension']
        totals['knowledge' if dimension == 'quiz' else dimension].append(
            (3 if value == 2 else 0) if dimension == 'quiz' else value)
    scores = {key: round(sum(values) / (3 * len(values)) * 100) for key, values in totals.items()}
    # Every dimension limits the profile; high appetite never offsets low capacity.
    bands = {key: 0 if value < 40 else 1 if value < 70 else 2 for key, value in scores.items()}
    level = min(bands.values())
    reasons = []
    for key, label in [('capacity', 'Sua capacidade financeira'), ('knowledge', 'Seu conhecimento e experiência'), ('tolerance', 'Sua tolerância a perdas')]:
        if bands[key] == level:
            reasons.append(label + ' limita o risco indicado pelas respostas.')
    for key, condition, text in [
        ('horizon', answers['horizon'] == 0, 'Prazo de até 1 ano: priorize o dinheiro necessário para esse objetivo.'),
        ('liquidity', answers['liquidity'] <= 1, 'Você pode precisar de boa parte do dinheiro em até 12 meses.'),
        ('reserve', answers['reserve'] == 0, 'Você ainda não tem reserva de emergência.'),
        ('debt', answers['debt'] == 0, 'Dívidas atrasadas ou caras pedem atenção antes de aumentar riscos.'),
        ('loss_capacity', answers['loss_capacity'] <= 1, 'Perdas comprometeriam despesas ou projetos essenciais.'),
        ('loss_tolerance', answers['loss_tolerance'] == 0, 'Você declarou que não aceita perdas temporárias.')]:
        if condition:
            level = 0
            reasons.append(text)
    if abs(scores['capacity'] - scores['tolerance']) >= 30:
        reasons.append('Sua disposição para risco e sua capacidade financeira diferem. Revise essa diferença antes de investir.')
    return {'version': VERSION, 'answers': dict(answers), 'profile': ['Conservador', 'Moderado', 'Arrojado'][level],
            'scores': scores, 'reasons': reasons}
