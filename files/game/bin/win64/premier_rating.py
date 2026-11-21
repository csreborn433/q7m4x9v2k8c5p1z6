"""Local bot-match rating rules, separate from profile XP and Valve matchmaking."""
import secrets

def initial(config):
    return {'rating': config['premier_start_rating'], 'wins': 0, 'losses': 0, 'ties': 0, 'last_change': 0}


def outcome(game_map, team):
    if team not in ('T', 'CT'): return None
    ct, terrorist = game_map.get('team_ct'), game_map.get('team_t')
    if not isinstance(ct, dict) or not isinstance(terrorist, dict): return None
    own, other = (ct.get('score'), terrorist.get('score')) if team == 'CT' else (terrorist.get('score'), ct.get('score'))
    if type(own) is not int or type(other) is not int or min(own, other) < 0 or own + other == 0: return None
    return 'wins' if own > other else 'losses' if own < other else 'ties'


def placement_rating(performance, config, randbelow):
    def stat(key):
        value = performance.get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError('Invalid placement statistic: ' + key)
        return value
    rounds = max(1, stat('rounds'))
    impact = (4 * stat('kills') + stat('assists') + 3 * stat('mvps')) * 1000 // rounds
    center = 1000 + min(8000, impact) - min(1000, stat('deaths') * 500 // rounds)
    center = max(500, min(9499, center))
    return max(1, min(9999, config['premier_max_rating'], center + randbelow(1001) - 500))


def apply(state, result, config, randbelow=None, performance=None):
    if result not in ('wins', 'losses', 'ties') or not config['premier_enabled']: return state.copy()
    updated = state.copy()
    updated[result] += 1
    if state['wins'] + state['losses'] + state['ties'] == 0:
        updated['rating'] = placement_rating(performance or {}, config, randbelow or secrets.randbelow)
        updated['last_change'] = 0
        return updated
    delta = config['premier_win_rating'] if result == 'wins' else -config['premier_loss_rating'] if result == 'losses' else 0
    variation = config.get('premier_rating_variation', 0)
    if delta and variation:
        jitter = (randbelow or secrets.randbelow)(variation * 2 + 1) - variation
        delta = max(1, delta + jitter) if delta > 0 else min(-1, delta + jitter)
    previous = updated['rating']
    updated['rating'] = max(0, min(config['premier_max_rating'], previous + delta))
    updated['last_change'] = updated['rating'] - previous
    return updated


def visible_rating(state, config):
    games = state['wins'] + state['losses'] + state['ties']
    return state['rating'] if games >= config['premier_placement_wins'] else None


def bot_difficulty(state):
    # Profile strength ramps separately; native hard starts at 25k, expert at 30k.
    rating = state['rating']
    return 0 if rating < 10000 else 1 if rating < 25000 else 2 if rating < 30000 else 3


def bot_preset(state):
    # Bot Improver skill presets (bot_skins.py) by local rating; the strongest bots from 30,000 (user's request).
    rating = state['rating']
    return 'Low' if rating < 20000 else 'Medium' if rating < 30000 else 'High'


def status(state, config):
    rating = visible_rating(state, config)
    return (f"Local CS Rating: {rating} ({state['last_change']:+d})" if rating is not None else
            f"Local Premier placement games: {state['wins'] + state['losses'] + state['ties']}/{config['premier_placement_wins']}")
