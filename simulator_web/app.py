from flask import Flask, render_template, request, redirect, url_for
from simulator_web.sim_logic import run_simulation

app = Flask(__name__, template_folder='templates', static_folder='static')


@app.route('/', methods=['GET'])
def index():
    # Default values for the form
    defaults = {
        'months': 6,
        'simulations': 1000,
        'sales_per_draw': 1500.0,
        'draws_per_week': 2,
        'billete_ratio': 0.5,
        'fixed_monthly_cost': 1200.0,
        'variable_cost_rate': 0.0,
        'customers': 500
    }
    return render_template('index.html', defaults=defaults)


@app.route('/run', methods=['POST'])
def run():
    # Read form inputs
    months = int(request.form.get('months', 6))
    simulations = int(request.form.get('simulations', 1000))
    sales_per_draw = float(request.form.get('sales_per_draw', 1500.0))
    draws_per_week = float(request.form.get('draws_per_week', 2))
    billete_ratio = float(request.form.get('billete_ratio', 0.5))
    fixed_monthly_cost = float(request.form.get('fixed_monthly_cost', 1200.0))
    variable_cost_rate = float(request.form.get('variable_cost_rate', 0.0))
    customers = int(request.form.get('customers', 500))

    result = run_simulation(months=months, simulations=simulations,
                            sales_per_draw=sales_per_draw, draws_per_week=draws_per_week,
                            billete_ratio=billete_ratio, fixed_monthly_cost=fixed_monthly_cost,
                            variable_cost_rate=variable_cost_rate, customers=customers)

    return render_template('results.html', params=request.form, result=result)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
