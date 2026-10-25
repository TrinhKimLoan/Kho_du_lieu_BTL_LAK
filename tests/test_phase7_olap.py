import unittest
from decimal import Decimal
from datetime import date
from src.marts.queries import sales_query,pivot


class Phase7OlapTests(unittest.TestCase):
    def test_unknown_dimensions_and_sources_fail(self):
        for dims in [('year; DROP TABLE dw.fact_sales',),('year','year')]:
            with self.assertRaises(ValueError):sales_query(dims)
        with self.assertRaises(ValueError):sales_query(source='raw.orders')
    def test_filter_values_are_bound_not_interpolated(self):
        value="RAM'); DROP TABLE dw.fact_sales;--"
        sql,params=sales_query(('category',),{'categories':[value]})
        self.assertNotIn(value,sql);self.assertEqual(params,[[value]])
    def test_date_range_is_half_open_and_typed(self):
        sql,params=sales_query(filters={'start':'2024-01-01','end':'2025-01-01'})
        self.assertIn('dp.full_date >= %s',sql);self.assertIn('dp.full_date < %s',sql)
        self.assertEqual(params,[date(2024,1,1),date(2025,1,1)])
    def test_invalid_filters_fail(self):
        for filters in [{'years':['2024']},{'categories':[]},{'categories':'RAM'},
                        {'start':'2025-01-01','end':'2024-01-01'},{'start':'2024-02-30'}, {'unknown':1}]:
            with self.assertRaises(ValueError):sales_query(filters=filters)
    def test_pivot_preserves_exact_decimal_money(self):
        rows=[{'category':'RAM','year':2024,'goods_amount':Decimal('0.10')},
              {'category':'RAM','year':2025,'goods_amount':Decimal('0.20')}]
        result=pivot(rows)
        self.assertEqual(result['rows'][0]['2024'],Decimal('0.10'))
        self.assertEqual(result['columns'],['category','2024','2025'])
    def test_pivot_refuses_to_sum_distinct_counts_from_duplicate_cells(self):
        rows=[{'category':'RAM','year':2024,'customer_count':1},
              {'category':'RAM','year':2024,'customer_count':1}]
        with self.assertRaises(ValueError):pivot(rows,value='customer_count')
    def test_pivot_does_not_average_averages(self):
        rows=[{'category':'RAM','year':2024,'avg_order_goods':Decimal('10')},
              {'category':'RAM','year':2024,'avg_order_goods':Decimal('100')}]
        with self.assertRaises(ValueError):pivot(rows,value='avg_order_goods')
    def test_missing_pivot_cells_remain_missing(self):
        rows=[{'category':'CPU','year':2024,'goods_amount':Decimal('10')},
              {'category':'RAM','year':2025,'goods_amount':Decimal('20')}]
        self.assertIsNone(pivot(rows)['rows'][0]['2025'])


if __name__=='__main__':unittest.main()
