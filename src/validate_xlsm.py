"""Validação estrutural da planilha final, sem depender do Excel."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile
import sys
import xml.etree.ElementTree as ET

from cfb_vba import CFB, decompress_container


ROOT = Path(__file__).resolve().parents[1]
XLSM = ROOT / "excel/Controle_Gastos_Automatico.xlsm"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
FORMULA_ERRORS = (
    "#REF!",
    "#DIV/0!",
    "#VALUE!",
    "#NAME?",
    "#N/A",
    "#NUM!",
    "#NULL!",
    "#SPILL!",
    "#CALC!",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(XLSM.is_file(), f"Arquivo não encontrado: {XLSM}")

    try:
        with ZipFile(XLSM) as workbook:
            require(workbook.testzip() is None, "O pacote XLSM contém um arquivo corrompido")
            names = set(workbook.namelist())
            require("xl/vbaProject.bin" in names, "O projeto VBA não está presente")

            root = ET.fromstring(workbook.read("xl/workbook.xml"))
            sheets = root.findall(f".//{{{MAIN_NS}}}sheet")
            visible = [
                sheet.attrib["name"]
                for sheet in sheets
                if sheet.attrib.get("state", "visible") == "visible"
            ]
            require(visible == ["Controle"], f"Abas visíveis inesperadas: {visible}")

            formulas: list[str] = []
            for name in names:
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    sheet = ET.fromstring(workbook.read(name))
                    formulas.extend(
                        node.text or "" for node in sheet.findall(f".//{{{MAIN_NS}}}f")
                    )
            require(formulas, "Nenhuma fórmula foi encontrada")
            bad_formulas = [
                formula
                for formula in formulas
                if any(error in formula for error in FORMULA_ERRORS)
            ]
            require(not bad_formulas, f"Fórmulas com erros: {bad_formulas[:5]}")

            drawing = workbook.read("xl/drawings/drawing1.xml")
            require(b"[0]!LancarGasto" in drawing, "Botão Lançar gasto sem macro")
            require(
                b"[0]!ExcluirLancamento" in drawing,
                "Botão Excluir selecionado sem macro",
            )

            project = CFB(workbook.read("xl/vbaProject.bin"))
            module = next(
                entry
                for entry in project.entries
                if entry["type"] == 2 and entry["name"] == "Módulo1"
            )
            source = decompress_container(project.stream(module)[11163:]).decode("cp1252")
            require("Public Sub LancarGasto()" in source, "Macro LancarGasto ausente")
            require(
                "Public Sub ExcluirLancamento()" in source,
                "Macro ExcluirLancamento ausente",
            )
    except (BadZipFile, KeyError, StopIteration, ET.ParseError) as exc:
        raise AssertionError(f"Estrutura XLSM inválida: {exc}") from exc

    print(
        f"OK: {XLSM.name}; 1 aba visível; {len(formulas)} fórmulas; "
        "2 macros e 2 botões validados."
    )


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
