-- 006_geography_seed.sql
-- Seed Australian state/territory dimension data
-- Works whether column is called geo_level (pre-015) or geo_type (post-015)

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'dim_geography' AND column_name = 'geo_type') THEN
        INSERT INTO dim_geography (geo_code, geo_name, geo_type, state)
        VALUES
            ('1', 'New South Wales', 'state', 'NSW'),
            ('2', 'Victoria', 'state', 'VIC'),
            ('3', 'Queensland', 'state', 'QLD'),
            ('4', 'South Australia', 'state', 'SA'),
            ('5', 'Western Australia', 'state', 'WA'),
            ('6', 'Tasmania', 'state', 'TAS'),
            ('7', 'Northern Territory', 'state', 'NT'),
            ('8', 'Australian Capital Territory', 'state', 'ACT')
        ON CONFLICT (geo_code, geo_type) DO NOTHING;
    ELSE
        INSERT INTO dim_geography (geo_code, geo_name, geo_level, state)
        VALUES
            ('1', 'New South Wales', 'state', 'NSW'),
            ('2', 'Victoria', 'state', 'VIC'),
            ('3', 'Queensland', 'state', 'QLD'),
            ('4', 'South Australia', 'state', 'SA'),
            ('5', 'Western Australia', 'state', 'WA'),
            ('6', 'Tasmania', 'state', 'TAS'),
            ('7', 'Northern Territory', 'state', 'NT'),
            ('8', 'Australian Capital Territory', 'state', 'ACT')
        ON CONFLICT (geo_code, geo_level) DO NOTHING;
    END IF;
END $$;
