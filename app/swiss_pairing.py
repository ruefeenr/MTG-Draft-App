def _opponent_name(entry):
    if isinstance(entry, (tuple, list)) and entry:
        return entry[0]
    return entry


def _played_pairs(sorted_players, opponents_by_player):
    players = set(sorted_players)
    played = set()
    for player in sorted_players:
        for opponent_entry in opponents_by_player.get(player, []):
            opponent = _opponent_name(opponent_entry)
            if not opponent or opponent == "BYE" or opponent not in players:
                continue
            played.add(frozenset((player, opponent)))
    return played


def generate_swiss_pairings(
    sorted_players,
    points_by_player,
    opponents_by_player,
    bye_counts_by_player,
):
    """
    Generate deterministic Swiss pairings with repeat avoidance as top priority.

    Returns:
    {
        "bye_player": str | None,
        "pairs": list[tuple[str, str]],
        "had_to_repeat": bool,
        "repeat_pairs": list[tuple[str, str]],
    }
    """
    sorted_players = list(sorted_players)
    rank_by_player = {player: index for index, player in enumerate(sorted_players)}
    played_pairs = _played_pairs(sorted_players, opponents_by_player)

    def points(player):
        return int(points_by_player.get(player, 0))

    def pair_key(player1, player2):
        return frozenset((player1, player2))

    def pair_repeat(player1, player2):
        return pair_key(player1, player2) in played_pairs

    def pair_score(player1, player2):
        rank_gap = abs(rank_by_player[player1] - rank_by_player[player2])
        score_gap = abs(points(player1) - points(player2))
        return (
            1 if pair_repeat(player1, player2) else 0,
            score_gap,
            rank_gap,
            tuple(sorted((player1, player2))),
        )

    def score_pairs(pairs, bye_player=None):
        repeat_pairs = [pair for pair in pairs if pair_repeat(pair[0], pair[1])]
        score_gaps = [abs(points(player1) - points(player2)) for player1, player2 in pairs]
        rank_gaps = [abs(rank_by_player[player1] - rank_by_player[player2]) for player1, player2 in pairs]
        pair_names = tuple(tuple(sorted(pair)) for pair in pairs)
        return (
            len(repeat_pairs),
            int(bye_counts_by_player.get(bye_player, 0)) if bye_player else 0,
            points(bye_player) if bye_player else 0,
            sum(score_gaps),
            max(score_gaps) if score_gaps else 0,
            sum(rank_gaps),
            (-(rank_by_player[bye_player]) if bye_player else 0, bye_player or "", pair_names),
        )

    def search_best_pairs(players):
        players = tuple(players)
        if not players:
            return (), ()

        first = players[0]
        rest = players[1:]
        best_score = None
        best_pairs = None
        opponents = sorted(rest, key=lambda candidate: pair_score(first, candidate))

        for opponent in opponents:
            remaining = tuple(player for player in rest if player != opponent)
            tail_score, tail_pairs = search_best_pairs(remaining)
            pairs = ((first, opponent),) + tail_pairs
            repeat_pairs = [pair for pair in pairs if pair_repeat(pair[0], pair[1])]
            score_gaps = [abs(points(player1) - points(player2)) for player1, player2 in pairs]
            rank_gaps = [abs(rank_by_player[player1] - rank_by_player[player2]) for player1, player2 in pairs]
            score = (
                len(repeat_pairs),
                sum(score_gaps),
                max(score_gaps) if score_gaps else 0,
                sum(rank_gaps),
                tuple(tuple(sorted(pair)) for pair in pairs),
                tail_score,
            )
            if best_score is None or score < best_score:
                best_score = score
                best_pairs = pairs

        return best_score, best_pairs

    def build_result(bye_player, pairs):
        repeat_pairs = [tuple(pair) for pair in pairs if pair_repeat(pair[0], pair[1])]
        return {
            "bye_player": bye_player,
            "pairs": [tuple(pair) for pair in pairs],
            "had_to_repeat": bool(repeat_pairs),
            "repeat_pairs": repeat_pairs,
        }

    if len(sorted_players) % 2 == 0:
        _, pairs = search_best_pairs(sorted_players)
        return build_result(None, pairs or ())

    bye_candidates = sorted(
        sorted_players,
        key=lambda player: (
            int(bye_counts_by_player.get(player, 0)),
            points(player),
            -rank_by_player[player],
            player,
        ),
    )

    best_variant_score = None
    best_variant = None
    for bye_player in bye_candidates:
        remaining = [player for player in sorted_players if player != bye_player]
        _, pairs = search_best_pairs(remaining)
        pairs = pairs or ()
        variant_score = score_pairs(pairs, bye_player=bye_player)
        if best_variant_score is None or variant_score < best_variant_score:
            best_variant_score = variant_score
            best_variant = (bye_player, pairs)

    bye_player, pairs = best_variant
    return build_result(bye_player, pairs)
