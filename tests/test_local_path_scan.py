import tempfile
import unittest
import zipfile
from pathlib import Path

from test_package import PackageCase
from verify_package import check_local_paths


class LocalPathScanTests(unittest.TestCase):
    def test_checks_workbook_xml_instead_of_binary_zip_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            path = package / "客户确认表.xlsx"
            with zipfile.ZipFile(path, "w") as workbook:
                workbook.writestr("xl/worksheets/sheet1.xml", "<text>产品资料</text>")
                workbook.writestr("xl/workbook.xml", '<workbook xmlns:ac="http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac"><ac:absPath url="D:/last-saved/"/></workbook>')
                workbook.comment = b"D:/"
            errors = []
            check_local_paths(package, [path.name], errors)
            self.assertEqual(errors, [])
            with zipfile.ZipFile(path, "a") as workbook:
                workbook.writestr("xl/sharedStrings.xml", "<text>C:/private/data</text>")
            check_local_paths(package, [path.name], errors)
            self.assertIn("Local machine path in 客户确认表.xlsx", errors)
