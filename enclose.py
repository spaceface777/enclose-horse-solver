import json
import pulp


def print_level_ansi(
    W,
    H,
    start_idx,
    water,
    portals,
    fruits,
    placed_walls,
    reachable_vars,
    cell_width=3,
):
    """
    Pretty prints the solved grid using ANSI escape codes.
    """
    ESC = "\033["
    RESET = f"{ESC}0m"

    def bg(code: int) -> str:
        return f"{ESC}48;5;{code}m"

    def fg(code: int) -> str:
        return f"{ESC}1;38;5;{code}m"

    def bg_rgb(rgb: int) -> str:
        return f"{ESC}48;2;{(rgb >> 16) & 0xFF};{(rgb >> 8) & 0xFF};{rgb & 0xFF}m"

    # different background colors for different cell types
    BG_WATER = bg_rgb(0x062F48)
    BG_WALL = bg_rgb(0x7B7979)
    BG_HORSE = bg(255)

    # Logic: Highlighting the "Enclosed" area vs "Outside"
    BG_INSIDE = bg_rgb(0xD1AE5A)
    BG_OUTSIDE = bg_rgb(0x208044)

    # Fruit Backgrounds
    BG_CHERRY = bg(160)  # Red
    BG_APPLE = bg(214)  # Gold
    BG_SKULL = bg(53)  # Purple/Dark Red

    FG_DARK = fg(16)
    FG_LIGHT = fg(231)

    # Pre-process portals for O(1) lookup: idx -> label
    portal_map = {}
    for label, indices in portals.items():
        for idx in indices:
            portal_map[idx] = label

    empty_cell = " " * cell_width

    print(f"\n{ESC}1m=== Optimal Enclosure ==={RESET}\n")

    # Header (X coordinates)
    # header = "   " + "".join(f"{x:>{cell_width}}" for x in range(W))
    # print(header)

    for r in range(H):
        # line_label = f"{r:>2} " # Y coordinate
        line_str = ""

        for c in range(W):
            idx = r * W + c

            # Determine logic state
            is_start = idx == start_idx
            is_wall_new = idx in placed_walls
            is_water = idx in water
            is_reachable = pulp.value(reachable_vars[idx]) > 0.5

            # Determine Background Color
            current_bg = BG_OUTSIDE  # Default

            if is_water:
                current_bg = BG_WATER
            elif is_wall_new:
                current_bg = BG_WALL
            elif is_start:
                current_bg = BG_HORSE
            elif is_reachable:
                current_bg = BG_INSIDE  # The "Enclosed" Grass

            # Determine Content (Glyphs)
            glyph = empty_cell
            current_fg = FG_LIGHT

            if is_start:
                glyph = "H".center(cell_width)
                current_fg = FG_DARK
            elif idx in fruits:
                # Fruit Logic (Override BG for specific items)
                val = fruits[idx]
                if val == 3:
                    current_bg = BG_CHERRY
                    glyph = "C".center(cell_width)
                elif val == 10:
                    current_bg = BG_APPLE
                    glyph = "G".center(cell_width)
                elif val == -5:
                    current_bg = BG_SKULL
                    glyph = "S".center(cell_width)
                current_fg = FG_DARK
            elif idx in portal_map:
                # Portals sit on top of the grass/reachability color
                glyph = portal_map[idx].center(cell_width)
                current_fg = FG_LIGHT
            elif is_wall_new:
                glyph = "#".center(cell_width)
                current_fg = FG_LIGHT

            line_str += f"{current_bg}{current_fg}{glyph}{RESET}"

        print(line_str)
    print(RESET + "\n")


def solve_enclose_horse(level_json, print_solved_board=True):
    # 1. Parse Input
    data = json.loads(level_json)
    map_str = data["map"]
    budget = data["budget"]

    rows = map_str.strip().split("\n")
    H = len(rows)
    W = len(rows[0])
    N = H * W

    # Identify entities
    start_idx = -1
    water = set()
    portals = {}
    fruits = {}

    def get_idx(r, c):
        return r * W + c

    print(f"Map: {data.get('name', 'Unknown')}")
    print(f"Size: {W}x{H} | Budget: {budget}")

    for r in range(H):
        for c in range(W):
            char = rows[r][c]
            idx = get_idx(r, c)

            if char == "H":
                start_idx = idx
            elif char == "~":
                water.add(idx)
            elif char == "C":
                fruits[idx] = 3
            elif char == "G":
                fruits[idx] = 10
            elif char == "S":
                fruits[idx] = -5
            elif char.isalnum():
                if char not in portals:
                    portals[char] = []
                portals[char].append(idx)

    borders = set()
    for r in range(H):
        borders.add(get_idx(r, 0))
        borders.add(get_idx(r, W - 1))
    for c in range(W):
        borders.add(get_idx(0, c))
        borders.add(get_idx(H - 1, c))

    # 2. Build Graph
    edges = []

    # Orthogonal
    for r in range(H):
        for c in range(W):
            u = get_idx(r, c)
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W:
                    v = get_idx(nr, nc)
                    edges.append((u, v))

    # Portal edges
    for p_nodes in portals.values():
        for i in range(len(p_nodes)):
            for j in range(len(p_nodes)):
                if i != j:
                    edges.append((p_nodes[i], p_nodes[j]))

    # 3. Setup ILP
    prob = pulp.LpProblem("EncloseHorse", pulp.LpMaximize)

    x = pulp.LpVariable.dicts("wall", range(N), 0, 1, pulp.LpBinary)
    y = pulp.LpVariable.dicts("reach", range(N), 0, 1, pulp.LpBinary)

    # Optimize flow variables: only create for non-water destination
    f = {}
    for u, v in edges:
        if v not in water and u not in water:
            f[(u, v)] = pulp.LpVariable(f"f_{u}_{v}", 0, N, pulp.LpContinuous)

    # Objective
    prob += pulp.lpSum([y[i] * (1 + fruits.get(i, 0)) for i in range(N)])

    # Constraints
    prob += pulp.lpSum([x[i] for i in range(N)]) <= budget

    prob += y[start_idx] == 1
    prob += x[start_idx] == 0

    for i in water:
        prob += x[i] == 0
        prob += y[i] == 0

    for i in borders:
        prob += y[i] == 0

    for p_list in portals.values():
        for i in p_list:
            prob += x[i] == 0

    for i in fruits:
        prob += x[i] == 0

    for i in range(N):
        if i not in water:
            prob += y[i] <= 1 - x[i]

    # Leak Constraints
    for u, v in edges:
        if v not in water and u not in water:
            prob += y[u] - y[v] <= x[v]

    # Connectivity
    for u, v in edges:
        if (u, v) in f:
            prob += f[(u, v)] <= N * y[u]
            prob += f[(u, v)] <= N * y[v]

    for i in range(N):
        if i == start_idx:
            continue
        if i in water:
            continue

        flow_in = pulp.lpSum([f.get((u, v), 0) for u, v in edges if v == i])
        flow_out = pulp.lpSum([f.get((u, v), 0) for u, v in edges if u == i])

        prob += flow_in - flow_out == y[i]

    # 4. Solve
    print("Solving ILP model...")
    # Using CBC with log disabled for cleaner output, re-enable if debugging
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if prob.status == pulp.LpStatusOptimal:
        wall_indices = {i for i in range(N) if pulp.value(x[i]) > 0.5}
        score = pulp.value(prob.objective)

        print(f"Status: Optimal Solution Found")
        print(f"Total Score: {int(score)}")
        print(f"Walls Used: {len(wall_indices)}/{budget}")

        if print_solved_board:
            # Call the pretty printer
            print_level_ansi(
                W, H, start_idx, water, portals, fruits, wall_indices, y
            )
        return wall_indices
    else:
        print(f"Status: {pulp.LpStatus[prob.status]}")
        return set()


# Input Data
level_json = '{"id":"qS_Kov","map":"...............\n.~.~~~~..~~~~~.\n.~...~...~...~.\n.~.1.......0.~.\n.~...~...~.....\n.~~..~...~.~~~.\n.......~.....~.\n....~..H...~...\n.~.......~.....\n.~~.~~.....~.~.\n.....~...~...~.\n.~G0....~~.1G~.\n.~...~...~.....\n.~~~~~...~~~~~.\n.......~.......","budget":10,"name":"4 Square","description":null,"creatorName":"Shivers","playCount":2503,"createdAt":1770427937,"isDaily":true,"dailyDate":"2026-02-08","dayNumber":41}'

if __name__ == "__main__":
    # check if level json is provided as a command line argument, otherwise use the hardcoded one
    import argparse

    parser = argparse.ArgumentParser(description="Solve an Enclose level with ILP.")
    parser.add_argument(
        "level",
        nargs="?",
        help="Path to level JSON file, or a raw JSON string. If omitted, uses hardcoded level data.",
    )
    parser.add_argument(
        "-n",
        "--no-solved-board",
        action="store_true",
        help="Do not print the solved ANSI board output.",
    )
    args = parser.parse_args()

    if args.level:
        try:
            with open(args.level, "r") as f:
                level_json = f.read()
        except Exception as e:
            # try to parse the argument as a json string directly
            try:
                json.loads(args.level)
                level_json = args.level
            except Exception as e:
                print(f"Error reading level data: {e}")
                print("Using hardcoded level data.")
    solve_enclose_horse(level_json, print_solved_board=not args.no_solved_board)
