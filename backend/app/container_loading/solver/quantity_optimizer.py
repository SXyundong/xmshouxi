from __future__ import annotations


def safe_max_quantity(item, container) -> int:
    volume_bound = int(container.physical_cbm / item.volume_m3) if item.volume_m3 else 0
    weight_bound = int(container.max_payload / item.carton_weight_kg) if item.carton_weight_kg else volume_bound
    return max(item.min_quantity, min(volume_bound, weight_bound))


def legal_min_quantity(item) -> int:
    return ((item.min_quantity + item.quantity_step - 1) // item.quantity_step) * item.quantity_step


def legal_max_quantity(item, container) -> int:
    upper = item.max_quantity if item.max_quantity is not None else safe_max_quantity(item, container)
    return (upper // item.quantity_step) * item.quantity_step


def quantity_is_valid(quantity, items, container) -> bool:
    total_volume = 0.0
    total_weight = 0.0
    for item in items:
        q = quantity.get(item.sku, 0)
        if q < legal_min_quantity(item) or q > legal_max_quantity(item, container) or q % item.quantity_step:
            return False
        total_volume += q * item.volume_m3
        total_weight += q * item.carton_weight_kg
    if total_weight > container.max_payload + 1e-9 or total_volume > container.physical_cbm + 1e-9:
        return False
    if container.operational_mode == "hard_limit" and total_volume > container.operational_target_cbm + 1e-9:
        return False
    return True


def quantity_search_info(items, container) -> tuple[dict[str, int], float, bool]:
    """Return a CP quantity candidate, a proven relaxation bound, and proof flag."""
    maxima = {item.sku: legal_max_quantity(item, container) for item in items}
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        volume = min(sum(maxima[i.sku] * i.volume_m3 for i in items),
                     container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm)
        return maxima, volume, False
    model = cp_model.CpModel()
    variables = {}
    scale = 1_000_000
    volume_terms = []
    for item in items:
        lo_k = legal_min_quantity(item) // item.quantity_step
        hi_k = legal_max_quantity(item, container) // item.quantity_step
        if lo_k > hi_k:
            return {}, 0.0, False
        variable = model.NewIntVar(lo_k, hi_k, f"q_{item.sku}")
        variables[item.sku] = variable
        volume_terms.append(variable * round(item.volume_m3 * item.quantity_step * scale))
    total_volume = sum(volume_terms)
    model.Add(sum(variables[i.sku] * round(i.carton_weight_kg * i.quantity_step * 1000) for i in items) <= round(container.max_payload * 1000))
    cbm_limit = container.operational_target_cbm if container.operational_mode == "hard_limit" else container.physical_cbm
    model.Add(total_volume <= round(cbm_limit * scale))
    model.Maximize(total_volume)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {}, 0.0, False
    quantities = {i.sku: int(solver.Value(variables[i.sku]) * i.quantity_step) for i in items}
    # For FEASIBLE, the incumbent objective is a lower bound. CP-SAT's best
    # objective bound is the only valid maximisation upper bound.
    upper_bound = max(0.0, float(solver.BestObjectiveBound())/scale)
    return quantities, upper_bound, status == cp_model.OPTIMAL


def quantity_upper_bound(items, container) -> tuple[dict[str, int], float]:
    candidate, upper, _ = quantity_search_info(items, container)
    return candidate, upper


def quantity_candidates(items, container, limit=40, **_ignored):
    """Compatibility helper; final quantities are decided by the 3D search."""
    cp_candidate, _, _ = quantity_search_info(items, container)
    if not cp_candidate:
        return []
    candidates = [
        cp_candidate,
        {item.sku: legal_max_quantity(item, container) for item in items},
        {item.sku: legal_min_quantity(item) for item in items},
    ]
    unique, seen = [], set()
    for candidate in candidates:
        key = tuple(candidate[i.sku] for i in items)
        if key not in seen and quantity_is_valid(candidate, items, container):
            seen.add(key)
            unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


