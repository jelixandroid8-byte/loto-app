import random
import numpy as np
import statistics

# Shared helpers and payouts (copied from simulator_financial)
COST_BILLETE = 1.00
COST_CHANCE = 0.25

PAY_BILLET = {
    'exact_p1': 2000,
    'exact_p2': 600,
    'exact_p3': 300,
    'p1_3digits': 50,
    'p1_2digits': 3,
    'p1_lastdigit': 1,
    'p1_2first_plus_last': 4,
    'p2_3digits': 20,
    'p2_2digits': 2,
    'p3_3digits': 10,
    'p3_2digits': 1
}

PAY_CHANCE = {
    'p1_2digits': 14,
    'p2_2digits': 3,
    'p3_2digits': 2
}

all4 = np.array([f"{i:04d}" for i in range(10000)])
all2 = np.array([f"{i:02d}" for i in range(100)])


def premio_counts(p1, p2, p3, counts4, counts2):
    prizes4 = np.zeros(10000, dtype=int)
    idx_p1, idx_p2, idx_p3 = int(p1), int(p2), int(p3)

    prizes4[idx_p1] = max(prizes4[idx_p1], PAY_BILLET['exact_p1'])
    prizes4[idx_p2] = max(prizes4[idx_p2], PAY_BILLET['exact_p2'])
    prizes4[idx_p3] = max(prizes4[idx_p3], PAY_BILLET['exact_p3'])

    mask = np.char.startswith(all4, p1[:3]) | np.char.endswith(all4, p1[-3:])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p1_3digits'])
    mask = np.char.startswith(all4, p1[:2]) | np.char.endswith(all4, p1[-2:])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p1_2digits'])
    mask = np.char.endswith(all4, p1[-1])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p1_lastdigit'])
    pattern = p1[:2] + p1[-1]
    mask = np.array([s[:2]+s[-1] == pattern for s in all4])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p1_2first_plus_last'])

    mask = np.char.startswith(all4, p2[:3]) | np.char.endswith(all4, p2[-3:])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p2_3digits'])
    mask = np.char.endswith(all4, p2[-2:])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p2_2digits'])

    mask = np.char.startswith(all4, p3[:3]) | np.char.endswith(all4, p3[-3:])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p3_3digits'])
    mask = np.char.endswith(all4, p3[-2:])
    prizes4[mask] = np.maximum(prizes4[mask], PAY_BILLET['p3_2digits'])

    payout_billetes = int((counts4 * prizes4).sum())

    prizes2 = np.zeros(100, dtype=int)
    prizes2[int(p1[-2:])] = max(prizes2[int(p1[-2:])], PAY_CHANCE['p1_2digits'])
    prizes2[int(p2[-2:])] = max(prizes2[int(p2[-2:])], PAY_CHANCE['p2_2digits'])
    prizes2[int(p3[-2:])] = max(prizes2[int(p3[-2:])], PAY_CHANCE['p3_2digits'])
    payout_chances = int((counts2 * prizes2).sum())

    return payout_billetes + payout_chances


def run_simulation(months=6, simulations=1000, sales_per_draw=1500.0,
                   draws_per_week=2, billete_ratio=0.5, fixed_monthly_cost=1200.0,
                   variable_cost_rate=0.0, customers=500):
    draws_per_month = draws_per_week * (52.0/12.0)
    draws_total = int(round(draws_per_month * months))

    profits = []
    times_to_profit = []

    for sim in range(simulations):
        cumulative_profit = 0.0
        profit_month = None

        for m in range(1, months+1):
            monthly_revenue = 0.0
            monthly_payout = 0.0

            n_draws = int(round(draws_per_month))
            for d in range(n_draws):
                # Distribute sales across customers to reflect realistic purchase counts
                total_sales = sales_per_draw
                # We model tickets sold as Poisson per customer so some buy more than others
                # First compute expected number of billetes and chances
                billete_sales = total_sales * billete_ratio
                chance_sales = total_sales * (1 - billete_ratio)

                # Compute units sold
                n_billetes = int(billete_sales / COST_BILLETE)
                n_chances = int(chance_sales / COST_CHANCE)

                counts4 = np.random.multinomial(n_billetes, [1/10000]*10000)
                counts2 = np.random.multinomial(n_chances, [1/100]*100)

                p_nums = random.sample(range(10000), 3)
                p1, p2, p3 = [f"{num:04d}" for num in p_nums]

                payout = premio_counts(p1, p2, p3, counts4, counts2)
                revenue = n_billetes*COST_BILLETE + n_chances*COST_CHANCE

                monthly_revenue += revenue
                monthly_payout += payout

            monthly_variable_cost = monthly_revenue * variable_cost_rate
            monthly_net = monthly_revenue - monthly_payout - fixed_monthly_cost - monthly_variable_cost

            cumulative_profit += monthly_net
            if profit_month is None and cumulative_profit > 0:
                profit_month = m

        profits.append(cumulative_profit)
        times_to_profit.append(profit_month if profit_month is not None else None)

    # produce summary
    mean = statistics.mean(profits)
    median = statistics.median(profits)
    percentiles = np.percentile(profits, [5,25,50,75,95]).tolist()
    prob_positive = sum(1 for p in profits if p>0)/len(profits)

    return {
        'months': months,
        'simulations': simulations,
        'mean': mean,
        'median': median,
        'percentiles': percentiles,
        'prob_positive': prob_positive,
        'profits_sample': profits[:20]
    }
