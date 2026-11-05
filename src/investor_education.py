"""A small educational questionnaire, stored with the authenticated account."""

QUESTION_KEYS = ('goal', 'horizon', 'liquidity', 'loss', 'knowledge')


def validate_education(value):
    if not isinstance(value, dict) or set(value) - {'experience', 'answers', 'profile', 'version'}:
        raise ValueError('Perfil de investidor inválido')
    experience = value.get('experience')
    if experience not in ('beginner', 'experienced', 'skipped'):
        raise ValueError('Escolha sua experiência com investimentos')
    answers = value.get('answers', {})
    if not isinstance(answers, dict) or (answers and set(answers) != set(QUESTION_KEYS)):
        raise ValueError('Responda todas as perguntas do perfil')
    if any(type(answer) is not int or not 0 <= answer <= 2 for answer in answers.values()):
        raise ValueError('Resposta de perfil inválida')
    profile = None
    if answers:
        # Short horizons, immediate cash needs and loss aversion override the score.
        score = sum(answers.values())
        if min(answers['horizon'], answers['liquidity'], answers['loss']) == 0 or score <= 3:
            profile = 'conservative'
        elif score >= 8 and answers['knowledge'] > 0:
            profile = 'aggressive'
        else:
            profile = 'moderate'
    return {'version': 1, 'experience': experience, 'answers': answers, 'profile': profile}
