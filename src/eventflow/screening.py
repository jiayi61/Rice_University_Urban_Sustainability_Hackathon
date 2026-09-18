"""Deterministic shuttle egress screening, not a calibrated city traffic forecast.

Conserves passengers by catchment. All passengers enter queues at event end.
Shared baseline service is allocated proportional to demand; added buses cycle
along each road route. Enumerate fleet options under a USD budget.
"""
import math


def number(inputs, key, default, low, high):
    value = inputs.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{key} must be between {low} and {high}.')
    return float(value)


def simulate_event(zones, routes, place, inputs, budget):
    total = sum(z['visitors'] for z in zones)
    service = number(inputs, 'baseline_service_pph', 12000, 100, 200000)
    seats = number(inputs, 'bus_seats', 45, 10, 100)
    load = number(inputs, 'load_factor', .85, .1, 1)
    dwell = number(inputs, 'dwell_minutes', 15, 1, 120)
    bus_cost = number(inputs, 'bus_cost_usd', 2500, 100, 100000)
    fleet_limit = int(number(inputs, 'fleet_limit', 100, 0, 500))
    cohort_pct = number(inputs, 'cohort_pct', 40, 1, 100)
    cohort = round(total * cohort_pct / 100)
    demands = [int(cohort * z['visitors'] / total) for z in zones]
    demands[-1] += cohort - sum(demands)
    weights = [d / cohort for d in demands]

    road_delay = number(inputs, 'road_delay_factor', 1.3, 1, 5)
    cycles = [(routes[z['zone_id']]['minutes'] + routes[z['zone_id']].get('return_minutes', routes[z['zone_id']]['minutes'])) * road_delay + dwell for z in zones]
    allocations = [[0] * len(zones)]
    # q²/(2*(a+b*n)) has diminishing marginal gains. Greedily assigning each
    # identical-cost bus to the largest gain is optimal for this separable model.
    for fleet in range(1, fleet_limit + 1):
        previous = allocations[-1]
        def gain(i):
            if demands[i] == 0:
                return 0
            added = seats * load * 60 / cycles[i]
            rate = service * weights[i] + previous[i] * added
            return demands[i]**2 / 2 * (1/rate - 1/(rate+added))
        chosen = max(range(len(zones)), key=gain)
        current = previous.copy()
        current[chosen] += 1
        allocations.append(current)

    def run(fleet, demand_factor=1., service_factor=1., delay_factor=1.):
        buses = allocations[fleet]
        rows = []
        for i, zone in enumerate(zones):
            route = routes[zone['zone_id']]
            cycle = (route['minutes'] + route.get('return_minutes', route['minutes'])) * road_delay * delay_factor + dwell
            rate = (service * weights[i] + buses[i] * seats * load * 60 / cycle) * service_factor
            demand = demands[i] * demand_factor
            rows.append({'name': zone['name'], 'people': demand, 'buses': buses[i], 'service_pph': round(rate, 2),
                         'cycle_minutes': round(cycle, 1), 'clearance_minutes': round(60 * demand / rate, 1) if rate else 0,
                         'queue_person_hours': demand * demand / (2 * rate) if rate else 0,
                         'distance_km': route['distance_km'], 'geometry': route['geometry'], 'source': route['source'],
                         'outbound_minutes': route['minutes'], 'return_minutes': route.get('return_minutes', route['minutes']),
                         'return_source': route.get('return_source', 'Assumed same as outbound'),
                         'zone_id': zone['zone_id']})
        end = max(r['clearance_minutes'] for r in rows)
        minutes = sorted(set([0, 30, 60, 90, 120, 180, 240, math.ceil(end)]))
        return {'fleet': fleet, 'cost_usd': round(fleet * bus_cost * 1.18), 'cohort': round(cohort * demand_factor),
                'clearance_minutes': end, 'queue_person_hours': round(sum(r['queue_person_hours'] for r in rows), 1),
                'served_120': round(sum(min(r['people'], r['service_pph'] * 2) for r in rows)), 'routes': rows,
                'timeline': [{'minute': t, 'remaining': round(sum(max(0, r['people'] - r['service_pph'] * t / 60) for r in rows))} for t in minutes]}

    baseline = run(0)
    options = [run(n) for n in range(fleet_limit + 1)]
    eligible = [p for p in options if budget is None or p['cost_usd'] <= budget]
    # Explicit objective: minimum queue-person-hours subject to fleet and budget.
    best = min(eligible, key=lambda p: (p['queue_person_hours'], p['cost_usd']))
    sensitivity = [{'demand_factor': d, 'service_factor': s,
                    'baseline': run(0, d, s)['clearance_minutes'],
                    'plan': run(best['fleet'], d, s)['clearance_minutes']}
                   for d in (.85, 1., 1.15) for s in (.85, 1., 1.15)]
    stress = [{'name': name, 'demand_factor': d, 'service_factor': s, 'road_delay_multiplier': t,
               'baseline_minutes': run(0,d,s,t)['clearance_minutes'], 'plan_minutes': run(best['fleet'],d,s,t)['clearance_minutes']}
              for name,d,s,t in [('Demand +25%',1.25,1,1),('Service -30%',1,.7,1),('Road times +50%',1,1,1.5),('Combined disruption',1.25,.7,1.5)]]
    return {'model': 'Fluid queues with marginal-benefit integer allocation v2', 'currency': 'USD',
            'budget_usd': budget, 'baseline': baseline, 'recommended': best, 'evaluated_portfolios': len(options),
            'frontier': [{k: p[k] for k in ('fleet', 'cost_usd', 'queue_person_hours', 'clearance_minutes')} for p in options],
            'sensitivity': sensitivity, 'stress_tests': stress, 'parameters': {'baseline_service_pph': service, 'bus_seats': seats, 'load_factor': load,
            'dwell_minutes': dwell, 'bus_cost_usd': bus_cost, 'fleet_limit': fleet_limit, 'cohort_pct': cohort_pct, 'road_delay_factor': road_delay},
            'limitations': [
                'Screening projection only: city-specific operating capacity and demand shares are not calibrated.',
                'Only the selected shuttle/shared-service cohort is modeled; remaining attendees are outside this simulation.',
                'Demand is allocated using assumed catchment shares, not ticketing or observed origin–destination data.',
                'Road routing is for proposed buses; it does not establish a rail route or transit timetable.',
                'Baseline service, bus availability, load, dwell and USD charter costs require local operator validation.',
                'All cohort passengers queue at event end. Bus cycle uses separate outbound and return road times when available, multiplied by an assumed event delay factor; network spillback is not modeled.',
                'Fleet allocation minimizes queue burden under fixed route demand, service, identical bus costs and unconstrained loading space. It is not a globally optimized multimodal network.',
                'Stress scenarios retain the selected route-by-route fleet allocation; road delay and demand multipliers are assumptions, not observed event effects.',
                'No city-specific carbon, heat, equity or safety benefit is asserted by this screening model.']}
