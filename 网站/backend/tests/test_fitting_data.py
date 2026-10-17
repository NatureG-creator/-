import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat
from backend.fitting_data import load_table, prepare_dataset


class FittingDataTests(unittest.TestCase):
    def test_header_group_and_validation_group_are_distinct(self):
        table = load_table(text='x,y,material,specimen\n1,2,A,a\n2,4,A,b\n3,6,B,c\n4,8,B,d')
        data = prepare_dataset(table, dict(x_column=0,y_column=1,group_column=2,validation_group_column=3))
        self.assertEqual(data['groups'], ['A','A','B','B'])
        self.assertEqual(data['validation_groups'], ['a','b','c','d'])
        self.assertEqual(data['row_ids'], [1,2,3,4])

    def test_no_header_keeps_first_row(self):
        self.assertEqual(load_table(text='0 1\n1 3\n2 5')['rows'][0], [0.,1.])

    def test_numeric_looking_identifiers_preserve_identity(self):
        table=load_table(text='x,y,id\n0,1,001\n1,2,001\n0,3,1\n1,4,1\n0,5,9007199254740992\n1,6,9007199254740992\n0,7,9007199254740993\n1,8,9007199254740993')
        data=prepare_dataset(table,dict(x_column=0,y_column=1,group_column=2,validation_group_column=2))
        self.assertEqual(data['groups'],['001','001','1','1','9007199254740992','9007199254740992','9007199254740993','9007199254740993'])
        self.assertEqual(data['validation_groups'],data['groups'])

    def test_missing_requires_explicit_drop_and_row_audit(self):
        table=load_table(text='x,y\n0,1\n1,\n2,5\n3,7')
        with self.assertRaisesRegex(ValueError,'第2行'):
            prepare_dataset(table,dict(x_column=0,y_column=1))
        data=prepare_dataset(table,dict(x_column=0,y_column=1,missing_policy='drop'))
        self.assertEqual(data['row_ids'],[1,3,4])
        self.assertEqual(data['audit']['invalid_rows'],[2])
        json.dumps(data,allow_nan=False)

    def test_internal_blank_rows_are_audited_not_renumbered(self):
        table=load_table(text='x,y\n0,1\n\n2,5\n3,7\n\n')
        data=prepare_dataset(table,dict(x_column=0,y_column=1,missing_policy='drop'))
        self.assertEqual(data['row_ids'],[1,3,4])
        self.assertEqual(data['audit']['invalid_rows'],[2])

    def test_exclusion_and_range_logged(self):
        data=prepare_dataset(load_table(text='0,1\n1,3\n2,5\n3,7\n4,9'),
                             dict(x_column=0,y_column=1,exclude_rows=[2],x_min=1))
        self.assertEqual(data['row_ids'],[3,4,5])
        self.assertEqual(data['audit']['excluded_rows'],[2])
        self.assertEqual(data['audit']['outside_range_rows'],[1])

    def test_nonpositive_sigma_and_boolean_column_rejected(self):
        table=load_table(text='1,2,0\n2,3,1\n3,4,1')
        with self.assertRaisesRegex(ValueError,'误差'):
            prepare_dataset(table,dict(x_column=0,y_column=1,sigma_column=2))
        with self.assertRaises(ValueError):
            prepare_dataset(table,dict(x_column=True,y_column=1))

    def test_xlsx_sheet_and_mat_ambiguity(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as d:
            book=openpyxl.Workbook(); book.active.title='first'
            book.active.append(['x','y']); book.active.append([1,2])
            book.create_sheet('second').append([3,4]); book.save(Path(d)/'data.xlsx');book.close()
            self.assertEqual(load_table(Path(d)/'data.xlsx',sheet='second')['rows'],[[3,4]])
            savemat(Path(d)/'data.mat',dict(a=np.ones((3,2)),b=np.zeros((4,2))))
            table=load_table(Path(d)/'data.mat')
            self.assertEqual(table['columns'],[])
            self.assertEqual(set(table['variables']),{'a','b'})
            self.assertEqual(len(load_table(Path(d)/'data.mat',variable='b')['rows']),4)

    def test_ragged_and_oversize_rejected(self):
        with self.assertRaises(ValueError):load_table(text='1,2\n3,4,5')
        with self.assertRaises(ValueError):load_table(text='1,2\n'*5001)


if __name__=='__main__':unittest.main()
