------------------------------------------ Load to dim_dates ---------------------------------------------------
CREATE OR REPLACE PROCEDURE gold.load_dim_dates()
LANGUAGE plpgsql
AS $$
DECLARE
    v_inserted INT := 0;
BEGIN
    INSERT INTO gold.dim_dates (date_id, date_day, date_month, date_year, is_weekday)
    SELECT 
		d::date AS date_id,
		EXTRACT(DAY FROM d)::int AS date_day,
		EXTRACT(MONTH FROM d)::int AS date_month,
		EXTRACT(YEAR FROM d)::int AS date_year,
		EXTRACT(isodow FROM d)::int <= 5 AS is_weekday
	FROM generate_series(
		(SELECT min(date) FROM silver.cleaned_rates),
		(SELECT max(date) FROM silver.cleaned_rates),
		INTERVAL '1 day'
		) AS d
	WHERE NOT EXISTS (
		SELECT 1 FROM gold.dim_dates dd WHERE dd.date_id = d::date
	);
 
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RAISE NOTICE 'load_dim_dates: inserted % new date(s).', v_inserted;
END;
$$;

------------------------------------------ Load to dim_currencies ---------------------------------------------------
CREATE OR REPLACE PROCEDURE gold.load_dim_currencies()
LANGUAGE plpgsql
AS $$
DECLARE
    v_inserted INT := 0;
BEGIN
    INSERT INTO gold.dim_currencies (currency_code, currenct_name, symbol, country)
    VALUES
        ('USD', 'US Dollar',     '$', 'United States'),
        ('EUR', 'Euro',          '€', 'European Union'),
        ('GBP', 'British Pound', '£', 'United Kingdom')
    ON CONFLICT (currency_code) DO NOTHING;
 
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RAISE NOTICE 'load_dim_currencies: inserted % new currency(ies).', v_inserted;
END;
$$;

------------------------------------------ Load to fct_aggregated_rates ---------------------------------------------------
CREATE OR REPLACE PROCEDURE gold.load_fct_rates()
LANGUAGE plpgsql
AS $$
DECLARE
    v_inserted INT := 0;
BEGIN
    INSERT INTO gold.fct_aggregated_rates (
        date,
        base_currency,
        target_currency,
        exchange_rate,
        rate_change_pct,
        seven_day_avg,
        load_timestamp
    )
    WITH new_rows AS (
        -- Only Silver rows not yet in Gold
        SELECT
            c.date,
            c.base_currency,
            c.target_currency,
            c.exchange_rate
        FROM silver.cleaned_rates c
        LEFT JOIN gold.fct_aggregated_rates f
            ON  c.date = f.date
            AND c.base_currency = f.base_currency
            AND c.target_currency = f.target_currency
        WHERE f.date IS NULL
    ),
    prev_rates AS (
	    -- Most recent rate before each new row's date from Silver
	    SELECT DISTINCT ON (n.date, n.base_currency, n.target_currency)
	        n.date,
	        n.base_currency,
	        n.target_currency,
	        s.exchange_rate AS prev_rate
	    FROM new_rows n
	    JOIN silver.cleaned_rates s
	        ON  s.base_currency   = n.base_currency
	        AND s.target_currency = n.target_currency
	        AND s.date            < n.date
	    ORDER BY
	        n.date,
	        n.base_currency,
	        n.target_currency,
	        s.date DESC
	),
    seven_day AS (
        -- Average of the 7 most recent trading days before each new row's date
        SELECT
            n.date,
            n.base_currency,
            n.target_currency,
            CASE
                WHEN COUNT(s.exchange_rate) >= 5   -- at least 5 trading days
                THEN ROUND(AVG(s.exchange_rate)::NUMERIC, 5)
                ELSE NULL
            END AS seven_day_avg
        FROM new_rows n
        JOIN silver.cleaned_rates s
            ON  s.base_currency = n.base_currency
            AND s.target_currency = n.target_currency
            AND s.date <  n.date
            AND s.date >= n.date - INTERVAL '7 days'
        GROUP BY
            n.date,
            n.base_currency,
            n.target_currency
    )
    SELECT
        n.date,
        n.base_currency,
        n.target_currency,
        n.exchange_rate,
        CASE
            WHEN p.prev_rate IS NULL OR p.prev_rate = 0 THEN NULL
            ELSE ROUND(
                ((n.exchange_rate - p.prev_rate) / p.prev_rate * 100)::NUMERIC,
                5
            )
        END AS rate_change_pct,
        sd.seven_day_avg,
        NOW() AS load_timestamp
    FROM new_rows n
    LEFT JOIN prev_rates p ON  p.date = n.date AND p.base_currency = n.base_currency AND p.target_currency = n.target_currency
    LEFT JOIN seven_day sd ON sd.date = n.date AND sd.base_currency  = n.base_currency AND sd.target_currency = n.target_currency
    -- Only insert currencies that exist in dim_currencies
    WHERE EXISTS (
        SELECT 1 FROM gold.dim_currencies dc
        WHERE dc.currency_code = n.target_currency
    )
	order by n.date
    ON CONFLICT (date, base_currency, target_currency) DO NOTHING;
 
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RAISE NOTICE 'load_fct_rates: inserted % new fact row(s).', v_inserted;
END;
$$;

------------------------------------------- Gold Pipeline Procedure ---------------------------------------------------
CREATE OR REPLACE PROCEDURE gold.run_gold_pipeline()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Gold pipeline: starting...';
    CALL gold.load_dim_currencies();
    CALL gold.load_dim_dates();
    CALL gold.load_fct_rates();
    RAISE NOTICE 'Gold pipeline: complete.';
END;
$$;