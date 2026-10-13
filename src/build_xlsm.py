from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
from cfb_vba import CFB, compress_container, decompress_container

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / 'build/Controle_Gastos_Automatico.xlsx'
XLSM = ROOT / 'excel/Controle_Gastos_Automatico.xlsm'
TEMPLATE = ROOT / 'src/template.bin'

macro = '''Attribute VB_Name = "Módulo1"\r
Option Explicit\r
\r
Public Sub LancarGasto()\r
    On Error GoTo TrataErro\r
    Dim ws As Worksheet\r
    Dim proximaLinha As Long\r
    Dim linha As Long\r
    Dim dataGasto As Date\r
    Dim valorGasto As Double\r
\r
    Set ws = ThisWorkbook.Worksheets("Controle")\r
\r
    If Not IsDate(ws.Range("I7").Value) Then\r
        MsgBox "Informe uma data válida.", vbExclamation, "Lançar gasto"\r
        ws.Range("I7").Select\r
        Exit Sub\r
    End If\r
    If Not IsNumeric(ws.Range("L7").Value) Or ws.Range("L7").Value <= 0 Then\r
        MsgBox "Informe um valor maior que zero.", vbExclamation, "Lançar gasto"\r
        ws.Range("L7").Select\r
        Exit Sub\r
    End If\r
    If Trim(CStr(ws.Range("O7").Value)) = "" Then\r
        MsgBox "Informe onde foi realizado o gasto.", vbExclamation, "Lançar gasto"\r
        ws.Range("O7").Select\r
        Exit Sub\r
    End If\r
\r
    dataGasto = CDate(ws.Range("I7").Value)\r
    valorGasto = CDbl(ws.Range("L7").Value)\r
    proximaLinha = 0\r
    For linha = 51 To 550\r
        If Len(Trim(CStr(ws.Cells(linha, "A").Value))) = 0 Then\r
            proximaLinha = linha\r
            Exit For\r
        End If\r
    Next linha\r
    If proximaLinha = 0 Then\r
        MsgBox "O histórico atingiu o limite de 500 lançamentos.", vbCritical, "Lançar gasto"\r
        Exit Sub\r
    End If\r
\r
    ws.Cells(proximaLinha, "A").Value = dataGasto\r
    ws.Cells(proximaLinha, "B").Value = Trim(CStr(ws.Range("O7").Value))\r
    ws.Cells(proximaLinha, "C").Value = Trim(CStr(ws.Range("I10").Value))\r
    ws.Cells(proximaLinha, "D").Value = Trim(CStr(ws.Range("L10").Value))\r
    ws.Cells(proximaLinha, "E").Value = Trim(CStr(ws.Range("O10").Value))\r
    ws.Cells(proximaLinha, "F").Value = valorGasto\r
    ws.Cells(proximaLinha, "G").Value = DateSerial(Year(dataGasto), Month(dataGasto), 1)\r
\r
    ws.Range("I7,L7,O7,I10,L10,O10").ClearContents\r
    ws.Range("I7").Value = Date\r
    Application.CalculateFull\r
    ws.Range("L7").Select\r
    MsgBox "Gasto lançado com sucesso!", vbInformation, "Lançar gasto"\r
    Exit Sub\r
\r
TrataErro:\r
    MsgBox "Não foi possível lançar o gasto: " & Err.Description, vbCritical, "Lançar gasto"\r
End Sub\r
\r
Public Sub ExcluirLancamento()\r
    On Error GoTo TrataErroExcluir\r
    Dim ws As Worksheet\r
    Dim linha As Long\r
    Dim resposta As VbMsgBoxResult\r
\r
    Set ws = ThisWorkbook.Worksheets("Controle")\r
    If ActiveSheet.Name <> ws.Name Then ws.Activate\r
    linha = ActiveCell.Row\r
\r
    If linha < 51 Or linha > 550 Or Len(Trim(CStr(ws.Cells(linha, "A").Value))) = 0 Then\r
        MsgBox "Primeiro clique em uma célula do gasto que deseja excluir no histórico.", vbExclamation, "Excluir lançamento"\r
        Exit Sub\r
    End If\r
\r
    resposta = MsgBox("Excluir o gasto de " & Format(ws.Cells(linha, "A").Value, "dd/mm/yyyy") & _\r
        " no valor de " & Format(ws.Cells(linha, "F").Value, "R$ #,##0.00") & "?", _\r
        vbYesNo + vbQuestion + vbDefaultButton2, "Confirmar exclusão")\r
    If resposta <> vbYes Then Exit Sub\r
\r
    ws.Range("A" & linha & ":G" & linha).ClearContents\r
    Application.CalculateFull\r
    MsgBox "Lançamento excluído.", vbInformation, "Excluir lançamento"\r
    Exit Sub\r
\r
TrataErroExcluir:\r
    MsgBox "Não foi possível excluir: " & Err.Description, vbCritical, "Excluir lançamento"\r
End Sub\r
'''.encode('cp1252')

project = CFB(TEMPLATE.read_bytes())
entries = {e['name']: e for e in project.entries if e['type'] == 2}
entry = entries['Módulo1']
stream = project.stream(entry)
offset = 11163
assert b'Attribute VB_Name = "M\xf3dulo1"' in decompress_container(stream[offset:])[:100]
project.replace_stream(entry, stream[:offset] + compress_container(macro))
version_entry = entries['_VBA_PROJECT']
version_stream = bytearray(project.stream(version_entry))
version_stream[2:4] = b'\xff\xff'
project.replace_stream(version_entry, bytes(version_stream))
vba_bytes = bytes(project.data)

button_shapes = '''<xdr:twoCellAnchor editAs="oneCell"><xdr:from><xdr:col>7</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>12</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>12</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>15</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:sp macro="[0]!LancarGasto" textlink=""><xdr:nvSpPr><xdr:cNvPr id="100" name="Lançar gasto"/><xdr:cNvSpPr/></xdr:nvSpPr><xdr:spPr><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="8F1D1D"/></a:solidFill><a:ln w="19050"><a:solidFill><a:srgbClr val="8F1D1D"/></a:solidFill></a:ln></xdr:spPr><xdr:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="pt-BR" sz="1400" b="1"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></a:rPr><a:t>LANÇAR GASTO</a:t></a:r><a:endParaRPr lang="pt-BR"/></a:p></xdr:txBody></xdr:sp><xdr:clientData/></xdr:twoCellAnchor><xdr:twoCellAnchor editAs="oneCell"><xdr:from><xdr:col>12</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>12</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>16</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>15</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:sp macro="[0]!ExcluirLancamento" textlink=""><xdr:nvSpPr><xdr:cNvPr id="101" name="Excluir lançamento selecionado"/><xdr:cNvSpPr/></xdr:nvSpPr><xdr:spPr><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="6B7280"/></a:solidFill><a:ln w="19050"><a:solidFill><a:srgbClr val="4B5563"/></a:solidFill></a:ln></xdr:spPr><xdr:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="pt-BR" sz="1200" b="1"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></a:rPr><a:t>EXCLUIR SELECIONADO</a:t></a:r><a:endParaRPr lang="pt-BR"/></a:p></xdr:txBody></xdr:sp><xdr:clientData/></xdr:twoCellAnchor>'''

with ZipFile(XLSX, 'r') as zin:
    parts = {name: zin.read(name) for name in zin.namelist()}

ct = ET.fromstring(parts['[Content_Types].xml'])
ns_ct = 'http://schemas.openxmlformats.org/package/2006/content-types'
for node in ct.findall(f'{{{ns_ct}}}Override'):
    if node.attrib.get('PartName') == '/xl/workbook.xml':
        node.set('ContentType', 'application/vnd.ms-excel.sheet.macroEnabled.main+xml')
if not any(n.attrib.get('PartName') == '/xl/workbook.xml' for n in ct.findall(f'{{{ns_ct}}}Override')):
    ET.SubElement(ct, f'{{{ns_ct}}}Override', PartName='/xl/workbook.xml', ContentType='application/vnd.ms-excel.sheet.macroEnabled.main+xml')
if not any(n.attrib.get('PartName') == '/xl/vbaProject.bin' for n in ct.findall(f'{{{ns_ct}}}Override')):
    ET.SubElement(ct, f'{{{ns_ct}}}Override', PartName='/xl/vbaProject.bin', ContentType='application/vnd.ms-office.vbaProject')
parts['[Content_Types].xml'] = ET.tostring(ct, encoding='utf-8', xml_declaration=True)

rels_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
wrels = ET.fromstring(parts['xl/_rels/workbook.xml.rels'])
ET.SubElement(wrels, f'{{{rels_ns}}}Relationship', Id='rIdVbaProject', Type='http://schemas.microsoft.com/office/2006/relationships/vbaProject', Target='vbaProject.bin')
parts['xl/_rels/workbook.xml.rels'] = ET.tostring(wrels, encoding='utf-8', xml_declaration=True)

main_ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
workbook_xml = ET.fromstring(parts['xl/workbook.xml'])
for sheet_node in workbook_xml.findall(f'.//{{{main_ns}}}sheet'):
    if sheet_node.attrib.get('name') != 'Controle':
        sheet_node.set('state', 'hidden')
parts['xl/workbook.xml'] = ET.tostring(workbook_xml, encoding='utf-8', xml_declaration=True)

sheet1_xml = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
for col in sheet1_xml.findall(f'.//{{{main_ns}}}col'):
    if int(col.attrib.get('min', '0')) <= 22 and int(col.attrib.get('max', '0')) >= 18:
        col.set('hidden', '1')
parts['xl/worksheets/sheet1.xml'] = ET.tostring(sheet1_xml, encoding='utf-8', xml_declaration=True)

drawing1 = parts['xl/drawings/drawing1.xml'].decode('utf-8-sig')
drawing1 = drawing1.replace('<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing">', '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">', 1)
drawing1 = drawing1.replace('</xdr:wsDr>', button_shapes + '</xdr:wsDr>')
parts['xl/drawings/drawing1.xml'] = drawing1.encode('utf-8')
parts['xl/vbaProject.bin'] = vba_bytes

with ZipFile(XLSM, 'w', ZIP_DEFLATED) as zout:
    for name, data in parts.items():
        zout.writestr(name, data)

with ZipFile(XLSM, 'r') as check:
    assert 'xl/vbaProject.bin' in check.namelist()
    assert b'[0]!LancarGasto' in check.read('xl/drawings/drawing1.xml')
    assert check.testzip() is None
print(XLSM)
