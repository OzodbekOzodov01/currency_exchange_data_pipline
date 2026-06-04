----------------------------------------- Database Creation ----------------------------------------------------------------------

CREATE DATABASE dwh_currency_exchange;

----------------------------------------- Scheama Creation -----------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

----------------------------------------- Bronze Table Creation ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.raw_rates(
	fetch_date varchar(225),
	base_currency varchar(225),
	raw_json varchar(225),
	inserted_at varchar(225)
);

ALTER TABLE bronze.raw_rates
ADD CONSTRAINT uq_raw_rates_date_base
UNIQUE (fetch_date, base_currency);

----------------------------------------- Silver Table Creation ------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS silver.seq_cleaned_rates
	START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 50;

CREATE TABLE IF NOT EXISTS silver.cleaned_rates(
	id bigint DEFAULT nextval('silver.seq_cleaned_rates'::regclass) NOT NULL,
	date date NOT NULL,
	base_currency char(3) NOT NULL,
	target_currency varchar(225) NOT NULL,
	exchange_rate decimal(10, 2) NOT NULL CHECK(exchange_rate > 0),
	load_timestamp timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT cleaned_rates_pk PRIMARY KEY (id)
);

----------------------------------------- Gold Table Creation -------------------------------------------------------------------
-- dim_dates
CREATE TABLE IF NOT EXISTS gold.dim_dates(
	date_id date NOT NULL,
	date_day int4 NOT NULL,
	date_month int4 NOT NULL,
	date_year int4 NOT NULL,
	is_weekday boolean NOT NULL,
	CONSTRAINT dim_dates_pk PRIMARY KEY (date_id)
);

-- dim_currencies
CREATE TABLE IF NOT EXISTS gold.dim_currencies(
	currency_code char(3) NOT NULL,
	currenct_name varchar(225) NOT NULL,
	symbol char(1) NOT NULL,
	country varchar(225) NOT NULL,
	CONSTRAINT dim_currencies_pk PRIMARY KEY (currency_code)
);

-- fct_aggregated_rates
CREATE SEQUENCE IF NOT EXISTS gold.seq_fct_aggregated_rates
	START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 50;

CREATE TABLE IF NOT EXISTS gold.fct_aggregated_rates(
	id bigint DEFAULT nextval('gold.seq_fct_aggregated_rates'::regclass) NOT NULL,
	date date NOT NULL,
	base_currency char(3) NOT NULL,
	target_currency char(3) NOT NULL,
	exchange_rate decimal(10, 2) NOT NULL,
	rate_change_pct decimal(10, 2),
	seven_day_avg decimal(10, 2),
	load_timestamp timestamptz DEFAULT now(),
	UNIQUE (date, base_currency, target_currency),
	CONSTRAINT fct_aggregated_rates_pk PRIMARY KEY (id),
	CONSTRAINT dim_dates_fk FOREIGN KEY (date) REFERENCES gold.dim_dates (date_id),
	CONSTRAINT dim_currencies_fk FOREIGN KEY (target_currency) REFERENCES gold.dim_currencies (currency_code)
);


--SELECT * FROM bronze.raw_rates rr;
--SELECT * FROM silver.cleaned_rates;
--
--CALL gold.load_dim_currencies();
--SELECT * FROM gold.dim_currencies dc;
--
--CALL gold.load_dim_dates();
--SELECT * FROM gold.dim_dates dd;
--
--CALL gold.load_fct_rates();
--SELECT * FROM gold.fct_aggregated_rates far;

