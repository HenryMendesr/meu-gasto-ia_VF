import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");

const wb=Workbook.create();
const controle=wb.worksheets.add("Controle");
const entrada=wb.worksheets.add("Preencha aqui");
const painel=wb.worksheets.add("Painel");
const lanc=wb.worksheets.add("Lançamentos");
const renda=wb.worksheets.add("Renda");
const carro=wb.worksheets.add("Carro");
const fixos=wb.worksheets.add("Fixos");
const estim=wb.worksheets.add("Estimativas");

const black="#111318", graphite="#242830", red="#C62828", redDark="#8F1D1D", white="#FFFFFF", light="#F4F5F7", gray="#6B7280", line="#D8DCE2", input="#FFF2CC", blue="#0000FF", green="#137333";
const money='R$ #,##0.00;[Red](R$ #,##0.00);-';
const pct='0.0%;[Red](0.0%);-';
const categories=["Alimentação","Mercado","Transporte","Moradia","Saúde","Educação","Lazer","Compras","Assinaturas","Contas","Viagem","Presentes","Outros"];
const payments=["Pix","Crédito","Débito","Dinheiro","Transferência","Voucher","Não informado"];
const setup=(s)=>{s.showGridLines=false;s.getRange("A1:Z1000").format.font={name:"Arial",size:10,color:black};};
const title=(s,range,text)=>{s.getRange(range).merge();s.getRange(range.split(":")[0]).values=[[text]];s.getRange(range).format={fill:black,font:{color:white,bold:true,size:16},verticalAlignment:"center"};};
const note=(s,range,text)=>{s.getRange(range).merge();s.getRange(range.split(":")[0]).values=[[text]];s.getRange(range).format={fill:"#FDECEC",font:{color:redDark,italic:true},verticalAlignment:"center"};};
const head=(r)=>{r.format={fill:graphite,font:{color:white,bold:true},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"thin",color:line}};};
const inputStyle=(r)=>{r.format={fill:input,font:{color:blue},verticalAlignment:"center",borders:{insideHorizontal:{style:"thin",color:"#E5E7EB"}}};};
for(const s of [controle,entrada,painel,lanc,renda,carro,fixos,estim]) setup(s);

// CONTROLE: única tela que o usuário precisa usar.
controle.getRange("A1:P550").format={fill:"#F7F8FA",font:{name:"Arial",size:10,color:"#1F2937"}};
title(controle,"A1:P2","Meu controle financeiro");
controle.getRange("A1:P2").format={fill:redDark,font:{color:white,bold:true,size:16},verticalAlignment:"center"};
note(controle,"A3:P3","Preencha somente os campos amarelos. Cada área foi separada para facilitar o uso.");
controle.getRange("A3:P3").format={fill:"#FDECEC",font:{color:redDark,italic:true},verticalAlignment:"center"};

controle.getRange("A5:F5").merge();controle.getRange("A5").values=[["DADOS DO MÊS"]];head(controle.getRange("A5:F5"));controle.getRange("A5:F5").format.fill=redDark;
controle.getRange("A7:B7").merge();controle.getRange("A7").values=[["Mês analisado"]];controle.getRange("A10:B10").merge();controle.getRange("A10").values=[["Salário líquido"]];
for(const r of ["A7:B7","A10:B10"]){controle.getRange(r).format={fill:"#E5E7EB",font:{color:"#1F2937",bold:true},verticalAlignment:"center"};}
for(const r of ["C7:F7","C10:F10"]){controle.getRange(r).merge();controle.getRange(r).format={fill:input,font:{color:blue,bold:true,size:13},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"thin",color:red}};}
controle.getRange("C7").values=[[new Date(Date.UTC(2026,8,1))]];controle.getRange("C7").setNumberFormat("mmmm yyyy");controle.getRange("C10").setNumberFormat(money);controle.getRange("C7").dataValidation={rule:{type:"list",formula1:"Renda!$A$5:$A$28"}};

controle.getRange("H5:P5").merge();controle.getRange("H5").values=[["LANÇAR UM GASTO"]];head(controle.getRange("H5:P5"));controle.getRange("H5:P5").format.fill=redDark;
controle.getRange("H7").values=[["1. Data"]];controle.getRange("K7").values=[["2. Valor"]];controle.getRange("N7").values=[["3. Onde"]];controle.getRange("H10").values=[["4. Categoria"]];controle.getRange("K10").values=[["5. Pagamento"]];controle.getRange("N10").values=[["6. Descrição"]];
for(const r of ["H7","K7","N7","H10","K10","N10"]){controle.getRange(r).format={fill:light,font:{color:black,bold:true},verticalAlignment:"center"};}
for(const r of ["I7:J7","L7:M7","O7:P7","I10:J10","L10:M10","O10:P10"]){controle.getRange(r).merge();controle.getRange(r).format={fill:input,font:{color:blue,bold:true},verticalAlignment:"center",borders:{preset:"outside",style:"thin",color:red}};}
controle.getRange("I7").setNumberFormat("dd/mm/yyyy");controle.getRange("L7").setNumberFormat(money);controle.getRange("I10").dataValidation={rule:{type:"list",values:categories}};controle.getRange("L10").dataValidation={rule:{type:"list",values:payments}};
controle.getRange("H13:L15").merge();controle.getRange("H13").values=[["LANÇAR GASTO"]];controle.getRange("H13:L15").format={fill:redDark,font:{color:white,bold:true,size:15},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"medium",color:redDark}};
controle.getRange("M13:P15").merge();controle.getRange("M13").values=[["EXCLUIR SELECIONADO"]];controle.getRange("M13:P15").format={fill:"#6B7280",font:{color:white,bold:true,size:12},horizontalAlignment:"center",verticalAlignment:"center",wrapText:true,borders:{preset:"outside",style:"medium",color:"#4B5563"}};

const summary=[
 ["A18:C18","A19:C22","Renda","=IF(C10=\"\",0,C10)"],
 ["E18:G18","E19:G22","Gastos","=SUMIFS($F$51:$F$550,$A$51:$A$550,\">=\"&$C$7,$A$51:$A$550,\"<\"&EDATE($C$7,1))"],
 ["I18:K18","I19:K22","Saldo","=A19-E19"],
 ["M18:P18","M19:P22","Fixos previstos","=SUMIFS($B$28:$B$37,$D$28:$D$37,\"Sim\")"]
];
for(const [hr,vr,label,formula] of summary){controle.getRange(hr).merge();controle.getRange(hr.split(":")[0]).values=[[label]];controle.getRange(hr).format={fill:redDark,font:{color:white,bold:true},horizontalAlignment:"center",verticalAlignment:"center"};controle.getRange(vr).merge();controle.getRange(vr.split(":")[0]).formulas=[[formula]];controle.getRange(vr).format={fill:white,font:{color:"#111827",bold:true,size:18},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"thin",color:"#D1D5DB"},numberFormat:money};}

controle.getRange("A26:D26").merge();controle.getRange("A26").values=[["GASTOS FIXOS MENSAIS"]];head(controle.getRange("A26:D26"));controle.getRange("A26:D26").format.fill=redDark;
controle.getRange("A27:D27").values=[["Descrição","Valor","Vencimento","Ativo"]];head(controle.getRange("A27:D27"));inputStyle(controle.getRange("A28:D37"));
controle.getRange("A28:A29").values=[["Parcela do carro"],["Gasolina"]];controle.getRange("B28:B37").setNumberFormat(money);controle.getRange("C28:C37").setNumberFormat("0");controle.getRange("D28:D37").dataValidation={rule:{type:"list",values:["Sim","Não"]}};controle.getRange("D28:D29").values=[["Sim"],["Sim"]];

controle.getRange("A40:D40").merge();controle.getRange("A40").values=[["DICA DO MÊS"]];head(controle.getRange("A40:D40"));controle.getRange("A40:D40").format.fill=redDark;controle.getRange("A41:D46").merge();controle.getRange("A41").formulas=[["=IF(C10=\"\",\"Digite seu salário para receber uma dica.\",IF(E19>C10,\"Seus gastos passaram do salário. Evite novas compras e revise os gastos fixos.\",IF(E19/C10>0.8,\"Atenção: você já gastou mais de 80% do salário. Reduza gastos não essenciais.\",IF(E19/C10>0.6,\"Seus gastos estão moderados. Controle lazer, compras e assinaturas.\",\"Boa! Seus gastos estão controlados. Tente guardar pelo menos 20% do salário.\"))))"]];controle.getRange("A41:D46").format={fill:white,font:{color:"#1F2937",bold:true,size:11},wrapText:true,verticalAlignment:"center",horizontalAlignment:"left",borders:{preset:"outside",style:"thin",color:"#D1D5DB"}};

controle.getRange("F26:K26").merge();controle.getRange("F26").formulas=[["=\"GASTOS DE \"&UPPER(TEXT($C$7,\"mmmm\"))"]];head(controle.getRange("F26:K26"));controle.getRange("F26:K26").format.fill=redDark;
controle.getRange("M26:P26").merge();controle.getRange("M26").formulas=[["=\"GASTOS DE \"&UPPER(TEXT(EDATE($C$7,-1),\"mmmm\"))"]];head(controle.getRange("M26:P26"));controle.getRange("M26:P26").format.fill=redDark;
controle.getRange("A50:G50").values=[["Data","Onde","Categoria","Pagamento","Descrição","Valor","Mês"]];head(controle.getRange("A50:G50"));controle.getRange("A50:G50").format.fill=redDark;
controle.getRange("A51:F51").values=[[new Date("2026-09-11T12:00:00Z"),"Gasolina","Transporte","Crédito","Lançamento preservado",71]];controle.getRange("G51").formulas=[["=IF(A51=\"\",\"\",DATE(YEAR(A51),MONTH(A51),1))"]];controle.getRange("G51:G550").fillDown();controle.getRange("A51:A550").setNumberFormat("dd/mm/yyyy");controle.getRange("F51:F550").setNumberFormat(money);controle.getRange("G51:G550").setNumberFormat("mmm-yy");controle.getRange("A51:F550").format={fill:white,font:{color:"#1F2937"},borders:{insideHorizontal:{style:"thin",color:"#E5E7EB"}}};controle.getRange("G51:G550").format={fill:"#F3F4F6",font:{color:"#6B7280"}};controle.tables.add("A50:G550",true,"TabelaControleGastos").style="TableStyleMedium2";

controle.getRange("R2:S2").values=[["Categoria","Mês atual"]];controle.getRange("U2:V2").values=[["Categoria","Mês anterior"]];
controle.getRange("R3:R15").values=categories.map(x=>[x]);controle.getRange("U3:U15").values=categories.map(x=>[x]);
for(let i=0;i<categories.length;i++){const r=3+i;controle.getRange(`S${r}`).formulas=[[`=SUMIFS($F$51:$F$550,$C$51:$C$550,R${r},$A$51:$A$550,\">=\"&$C$7,$A$51:$A$550,\"<\"&EDATE($C$7,1))`]];controle.getRange(`V${r}`).formulas=[[`=SUMIFS($F$51:$F$550,$C$51:$C$550,U${r},$A$51:$A$550,\">=\"&EDATE($C$7,-1),$A$51:$A$550,\"<\"&$C$7)`]];}
controle.getRange("S3:S15").setNumberFormat(money);controle.getRange("V3:V15").setNumberFormat(money);
const currentChart=controle.charts.add("bar",controle.getRange("R2:S15"),"Auto");currentChart.title.text="Por categoria — mês atual";currentChart.setPosition(controle.getRange("F27:K44"));currentChart.width=510;currentChart.height=370;currentChart.hasLegend=false;if(currentChart.series.items[0])currentChart.series.items[0].fill={type:"solid",color:red};
const previousChart=controle.charts.add("bar",controle.getRange("U2:V15"),"Auto");previousChart.title.text="Por categoria — mês anterior";previousChart.setPosition(controle.getRange("M27:P44"));previousChart.width=430;previousChart.height=370;previousChart.hasLegend=false;if(previousChart.series.items[0])previousChart.series.items[0].fill={type:"solid",color:"#6B7280"};
controle.getRange("A:A").format.columnWidth=23;controle.getRange("B:D").format.columnWidth=18;controle.getRange("E:G").format.columnWidth=15;controle.getRange("H:P").format.columnWidth=15;controle.getRange("R:V").format.columnWidth=2;
for(const r of [4,6,8,9,11,12,16,17,23,24,25,38,39,47,48,49])controle.getRange(`${r}:${r}`).format.rowHeight=10;
for(const r of [7,10,13,14,15,18,19,20,21,22,26,40,50])controle.getRange(`${r}:${r}`).format.rowHeight=25;
controle.freezePanes.freezeRows(3);

// ABA CENTRAL DE ENTRADAS: somente as células amarelas recebem digitação.
title(entrada,"A1:J2","Preencha aqui");
note(entrada,"A3:J3","Digite somente nas células amarelas. As células cinzas e brancas são resultados automáticos.");
entrada.getRange("A5:D5").merge();entrada.getRange("A5").values=[["RENDA MENSAL — DIGITE AQUI"]];head(entrada.getRange("A5:D5"));
entrada.getRange("A6:D6").values=[["Mês","Salário líquido","Renda extra","Outras entradas"]];head(entrada.getRange("A6:D6"));
const inputMonths=[];for(let y=2026;y<=2027;y++)for(let m=0;m<12;m++)inputMonths.push([new Date(Date.UTC(y,m,1)),null,null,null]);
entrada.getRange("A7:D30").values=inputMonths;inputStyle(entrada.getRange("B7:D30"));
entrada.getRange("A7:A30").setNumberFormat("mmm-yy");entrada.getRange("B7:D30").setNumberFormat(money);entrada.getRange("A7:D30").format.borders={insideHorizontal:{style:"thin",color:"#E5E7EB"}};

entrada.getRange("F5:J5").merge();entrada.getRange("F5").values=[["CARRO E GASOLINA — DIGITE AQUI"]];head(entrada.getRange("F5:J5"));
const carInputs=[["F7","Saldo devedor atual",null],["F9","Parcelas restantes",null],["F11","Próximo vencimento",null],["F13","Valor da parcela atual",null],["F15","Orçamento mensal de gasolina",null],["F17","Taxa de juros mensal",0.012]];
for(const [cell,label,value] of carInputs){const row=Number(cell.slice(1));entrada.getRange(`F${row}:H${row}`).merge();entrada.getRange(`F${row}`).values=[[label]];entrada.getRange(`F${row}:H${row}`).format={fill:graphite,font:{color:white,bold:true},verticalAlignment:"center"};entrada.getRange(`I${row}:J${row}`).merge();if(value!==null)entrada.getRange(`I${row}`).values=[[value]];entrada.getRange(`I${row}:J${row}`).format={fill:input,font:{color:blue,bold:true,size:12},horizontalAlignment:"center",borders:{preset:"outside",style:"thin",color:red}};}
entrada.getRange("I7:J7").setNumberFormat(money);entrada.getRange("I11:J11").setNumberFormat("dd/mm/yyyy");entrada.getRange("I13:J15").setNumberFormat(money);entrada.getRange("I17:J17").setNumberFormat("0.0%");entrada.getRange("I9:J9").dataValidation={rule:{type:"whole",operator:"between",formula1:1,formula2:600}};
entrada.getRange("F20:J20").merge();entrada.getRange("F20").values=[["RESULTADOS AUTOMÁTICOS — NÃO DIGITE"]];head(entrada.getRange("F20:J20"));
const autoRows=[[22,"Parcela calculada","=IF(OR(I7=\"\",I17=\"\",I9=\"\"),\"\",-PMT(I17,I9,I7))",money],[24,"Total restante estimado","=IF(OR(I7=\"\",I9=\"\"),\"\",IF(I13<>\"\",I13*I9,I22*I9))",money],[26,"Juros estimados","=IF(OR(I24=\"\",I7=\"\"),\"\",MAX(0,I24-I7))",money],[28,"Quitação estimada","=IF(OR(I11=\"\",I9=\"\"),\"\",EDATE(I11,I9-1))","dd/mm/yyyy"],[30,"Carro + gasolina por mês","=IF(AND(I13=\"\",I22=\"\",I15=\"\"),\"\",IF(I13<>\"\",I13,I22)+IF(I15=\"\",0,I15))",money]];
for(const [row,label,formula,fmt] of autoRows){entrada.getRange(`F${row}:H${row}`).merge();entrada.getRange(`F${row}`).values=[[label]];entrada.getRange(`F${row}:H${row}`).format={fill:light,font:{color:black,bold:true}};entrada.getRange(`I${row}:J${row}`).merge();entrada.getRange(`I${row}`).formulas=[[formula]];entrada.getRange(`I${row}:J${row}`).format={fill:white,font:{color:black,bold:true,size:12},horizontalAlignment:"center",borders:{preset:"outside",style:"thin",color:line},numberFormat:fmt};}
entrada.getRange("A:A").format.columnWidth=15;entrada.getRange("B:D").format.columnWidth=20;entrada.getRange("E:E").format.columnWidth=4;entrada.getRange("F:H").format.columnWidth=17;entrada.getRange("I:J").format.columnWidth=16;entrada.freezePanes.freezeRows(6);

// LANÇAMENTOS REAIS: formulário de uma linha + histórico preenchido pelo botão VBA.
title(lanc,"A1:J2","Gastos — fácil e rápido");
note(lanc,"A3:J3","1) Preencha os campos amarelos  •  2) Clique em LANÇAR  •  Para apagar, selecione o gasto no histórico e clique em EXCLUIR.");
lanc.getRange("A5").values=[["1. Data"]];lanc.getRange("C5").values=[["2. Valor"]];lanc.getRange("E5").values=[["3. Onde gastou"]];lanc.getRange("A7").values=[["4. Categoria"]];lanc.getRange("C7").values=[["5. Pagamento"]];lanc.getRange("E7").values=[["6. Descrição"]];
for(const r of ["A5","C5","E5","A7","C7","E7"]){lanc.getRange(r).format={fill:graphite,font:{color:white,bold:true},horizontalAlignment:"center",verticalAlignment:"center"};}
for(const r of ["B5","D5","F5","B7","D7","F7"]){lanc.getRange(r).format={fill:input,font:{color:blue,bold:true,size:11},borders:{preset:"outside",style:"thin",color:red}};}
lanc.getRange("B5").setNumberFormat("dd/mm/yyyy");lanc.getRange("D5").setNumberFormat(money);lanc.getRange("B7").dataValidation={rule:{type:"list",values:categories}};lanc.getRange("D7").dataValidation={rule:{type:"list",values:payments}};
lanc.getRange("G5:H7").merge();lanc.getRange("G5").values=[["LANÇAR GASTO"]];lanc.getRange("G5:H7").format={fill:redDark,font:{color:white,bold:true,size:14},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"medium",color:redDark}};
lanc.getRange("I5:J7").merge();lanc.getRange("I5").values=[["EXCLUIR\nSELECIONADO"]];lanc.getRange("I5:J7").format={fill:"#6B7280",font:{color:white,bold:true,size:12},horizontalAlignment:"center",verticalAlignment:"center",wrapText:true,borders:{preset:"outside",style:"medium",color:"#4B5563"}};
lanc.getRange("A9:J9").merge();lanc.getRange("A9").values=[["Dica: para corrigir um erro, clique em qualquer célula da linha no histórico e use EXCLUIR SELECIONADO."]];lanc.getRange("A9:J9").format={fill:"#FFF7E6",font:{color:"#92400E",bold:true},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"thin",color:"#F59E0B"}};
lanc.getRange("A11:G11").values=[["Data","Onde","Categoria","Pagamento","Descrição","Valor","Mês"]];head(lanc.getRange("A11:G11"));
lanc.getRange("A12:F12").values=[[new Date("2026-09-11T12:00:00Z"),"Gasolina","Transporte","Crédito","Lançamento preservado da versão anterior",71]];
lanc.getRange("G12").formulas=[["=IF(A12=\"\",\"\",DATE(YEAR(A12),MONTH(A12),1))"]];lanc.getRange("G12:G511").fillDown();
lanc.getRange("A12:F511").format={fill:white,font:{color:black},borders:{insideHorizontal:{style:"thin",color:"#E5E7EB"}}};lanc.getRange("G12:G511").format={fill:light,font:{color:gray},horizontalAlignment:"center"};
lanc.getRange("A12:A511").setNumberFormat("dd/mm/yyyy");lanc.getRange("F12:F511").setNumberFormat(money);lanc.getRange("G12:G511").setNumberFormat("mmm-yy");
lanc.getRange("F12:F511").conditionalFormats.add("cellIs",{operator:"lessThan",formula:0,format:{fill:"#FECACA",font:{color:"#991B1B",bold:true}}});
lanc.tables.add("A11:G511",true,"TabelaLancamentos").style="TableStyleMedium2";lanc.freezePanes.freezeRows(11);
lanc.getRange("A:A").format.columnWidth=15;lanc.getRange("B:B").format.columnWidth=22;lanc.getRange("C:D").format.columnWidth=18;lanc.getRange("E:E").format.columnWidth=34;lanc.getRange("F:G").format.columnWidth=16;lanc.getRange("H:J").format.columnWidth=15;

// RENDA MENSAL
title(renda,"A1:E2","Renda mensal — automático");
note(renda,"A3:E3","Esta aba é automática. Preencha os valores somente na aba 'Preencha aqui'.");
renda.getRange("A4:E4").values=[["Mês","Salário líquido","Renda extra","Outras entradas","Renda total"]];head(renda.getRange("A4:E4"));
const months=[];for(let y=2026;y<=2027;y++)for(let m=0;m<12;m++)months.push([new Date(Date.UTC(y,m,1)),null,null,null]);
renda.getRange("A5:A28").values=months.map(x=>[x[0]]);renda.getRange("B5:D5").formulas=[["='Preencha aqui'!B7","='Preencha aqui'!C7","='Preencha aqui'!D7"]];renda.getRange("B5:D28").fillDown();
renda.getRange("B5:D28").format={fill:light,font:{color:gray}};
renda.getRange("E5").formulas=[["=SUM(B5:D5)"]];renda.getRange("E5:E28").fillDown();renda.getRange("E5:E28").format.font={color:black};
renda.getRange("A5:A28").setNumberFormat("mmm-yy");renda.getRange("B5:E28").setNumberFormat(money);renda.getRange("A5:E28").format.borders={insideHorizontal:{style:"thin",color:"#E5E7EB"}};
renda.tables.add("A4:E28",true,"TabelaRenda").style="TableStyleMedium2";renda.freezePanes.freezeRows(4);
renda.getRange("A:A").format.columnWidth=14;renda.getRange("B:E").format.columnWidth=20;

// CARRO: DADOS DO FINANCIAMENTO E REGISTRO EXCLUSIVO
title(carro,"A1:J2","Carro e gasolina");
note(carro,"A3:J3","Esta parte é automática. Informe os dados do financiamento na aba 'Preencha aqui'.");
carro.getRange("A4:J4").values=[["Valor restante do carro","","Taxa mensal","","Parcelas restantes","","Próximo vencimento","","",""]];
carro.getRange("A5:J5").values=[["Parcela informada","","Orçamento mensal de gasolina","","Parcela calculada","","Quitação estimada","","",""]];
carro.getRange("A6:J6").values=[["Total restante estimado","","Juros estimados","","Carro + gasolina por mês","","","","",""]];
for(const r of ["A4","C4","E4","G4","A5","C5","E5","G5","A6","C6","E6"]){carro.getRange(r).format={fill:graphite,font:{color:white,bold:true},verticalAlignment:"center"};}
for(const r of ["B4","D4","F4","H4","B5","D5"]){carro.getRange(r).format={fill:light,font:{color:gray,bold:true},borders:{preset:"outside",style:"thin",color:line}};}
carro.getRange("B4").formulas=[["=IF('Preencha aqui'!I7=\"\",\"\",'Preencha aqui'!I7)"]];carro.getRange("D4").formulas=[["='Preencha aqui'!I17"]];carro.getRange("F4").formulas=[["=IF('Preencha aqui'!I9=\"\",\"\",'Preencha aqui'!I9)"]];carro.getRange("H4").formulas=[["=IF('Preencha aqui'!I11=\"\",\"\",'Preencha aqui'!I11)"]];carro.getRange("B5").formulas=[["=IF('Preencha aqui'!I13=\"\",\"\",'Preencha aqui'!I13)"]];carro.getRange("D5").formulas=[["=IF('Preencha aqui'!I15=\"\",\"\",'Preencha aqui'!I15)"]];carro.getRange("D4").setNumberFormat("0.0%");
carro.getRange("B4:B6").setNumberFormat(money);carro.getRange("B5:D6").setNumberFormat(money);carro.getRange("F5:F6").setNumberFormat(money);carro.getRange("H4:H5").setNumberFormat("dd/mm/yyyy");
carro.getRange("F5").formulas=[["=IF(OR(B4=\"\",D4=\"\",F4=\"\"),\"\",-PMT(D4,F4,B4))"]];
carro.getRange("H5").formulas=[["=IF(OR(H4=\"\",F4=\"\"),\"\",EDATE(H4,F4-1))"]];
carro.getRange("B6").formulas=[["=IF(OR(B4=\"\",F4=\"\"),\"\",IF(B5<>\"\",B5*F4,F5*F4))"]];
carro.getRange("D6").formulas=[["=IF(OR(B6=\"\",B4=\"\"),\"\",MAX(0,B6-B4))"]];
carro.getRange("F6").formulas=[["=IF(AND(B5=\"\",F5=\"\",D5=\"\"),\"\",IF(B5<>\"\",B5,F5)+IF(D5=\"\",0,D5))"]];

carro.getRange("A9:F9").values=[["Data","Tipo","Pagamento","Observação","Valor","Mês"]];head(carro.getRange("A9:F9"));inputStyle(carro.getRange("A10:E209"));
carro.getRange("B10:B209").dataValidation={rule:{type:"list",values:["Parcela do carro","Gasolina"]}};carro.getRange("C10:C209").dataValidation={rule:{type:"list",values:payments}};
carro.getRange("F10").formulas=[["=IF(A10=\"\",\"\",DATE(YEAR(A10),MONTH(A10),1))"]];carro.getRange("F10:F209").fillDown();carro.getRange("F10:F209").format={fill:light,font:{color:gray}};
carro.getRange("A10:A209").setNumberFormat("dd/mm/yyyy");carro.getRange("E10:E209").setNumberFormat(money);carro.getRange("F10:F209").setNumberFormat("mmm-yy");carro.tables.add("A9:F209",true,"TabelaCarro").style="TableStyleMedium2";

carro.getRange("H9:J9").values=[["Mês","Parcela paga","Gasolina"]];head(carro.getRange("H9:J9"));
for(let i=0;i<24;i++){const r=10+i,src=5+i;carro.getRange(`H${r}`).formulas=[[`=TEXT(Renda!A${src},\"mmm-yy\")`]];carro.getRange(`I${r}`).formulas=[[`=SUMIFS($E$10:$E$209,$B$10:$B$209,\"Parcela do carro\",$A$10:$A$209,\">=\"&Renda!A${src},$A$10:$A$209,\"<\"&EDATE(Renda!A${src},1))`]];carro.getRange(`J${r}`).formulas=[[`=SUMIFS($E$10:$E$209,$B$10:$B$209,\"Gasolina\",$A$10:$A$209,\">=\"&Renda!A${src},$A$10:$A$209,\"<\"&EDATE(Renda!A${src},1))`]];}
carro.getRange("I10:J33").setNumberFormat(money);
const carChart=carro.charts.add("line",carro.getRange("H9:J33"),"Auto");carChart.title.text="Parcela do carro e gasolina por mês";carChart.setPosition(carro.getRange("H35:N52"));carChart.width=620;carChart.height=310;carChart.hasLegend=true;carChart.legend.position="top";if(carChart.series.items[0])carChart.series.items[0].line={fill:red,style:"solid",width:2};if(carChart.series.items[1])carChart.series.items[1].line={fill:"#F59E0B",style:"solid",width:2};
carro.freezePanes.freezeRows(9);carro.getRange("A:A").format.columnWidth=29;carro.getRange("B:B").format.columnWidth=19;carro.getRange("C:C").format.columnWidth=31;carro.getRange("D:D").format.columnWidth=22;carro.getRange("E:E").format.columnWidth=23;carro.getRange("F:F").format.columnWidth=17;carro.getRange("G:G").format.columnWidth=25;carro.getRange("H:J").format.columnWidth=18;

// GASTOS FIXOS
title(fixos,"A1:G2","Gastos fixos");
note(fixos,"A3:G3","Cadastre cada gasto recorrente uma vez. O painel inclui automaticamente os itens ativos no mês selecionado.");
fixos.getRange("A4:G4").values=[["Descrição","Categoria","Pagamento","Valor mensal","Início","Fim opcional","Ativo"]];head(fixos.getRange("A4:G4"));inputStyle(fixos.getRange("A5:G204"));
fixos.getRange("B5:B204").dataValidation={rule:{type:"list",values:categories}};fixos.getRange("C5:C204").dataValidation={rule:{type:"list",values:payments}};fixos.getRange("G5:G204").dataValidation={rule:{type:"list",values:["Sim","Não"]}};
fixos.getRange("D5:D204").setNumberFormat(money);fixos.getRange("E5:F204").setNumberFormat("dd/mm/yyyy");
fixos.tables.add("A4:G204",true,"TabelaFixos").style="TableStyleMedium2";fixos.freezePanes.freezeRows(4);
fixos.getRange("A:A").format.columnWidth=28;fixos.getRange("B:C").format.columnWidth=18;fixos.getRange("D:D").format.columnWidth=18;fixos.getRange("E:F").format.columnWidth=15;fixos.getRange("G:G").format.columnWidth=12;

// ESTIMATIVAS
title(estim,"A1:D2","Estimativas mensais");
note(estim,"A3:D3","Use para mercado, gasolina, água, luz e outros valores que variam no mês.");
estim.getRange("A4:D4").values=[["Mês","Descrição","Categoria","Valor estimado"]];head(estim.getRange("A4:D4"));inputStyle(estim.getRange("A5:D304"));
estim.getRange("A5:A304").setNumberFormat("mmm-yy");estim.getRange("C5:C304").dataValidation={rule:{type:"list",values:categories}};estim.getRange("D5:D304").setNumberFormat(money);
estim.tables.add("A4:D304",true,"TabelaEstimativas").style="TableStyleMedium2";estim.freezePanes.freezeRows(4);
estim.getRange("A:A").format.columnWidth=15;estim.getRange("B:B").format.columnWidth=30;estim.getRange("C:C").format.columnWidth=20;estim.getRange("D:D").format.columnWidth=20;

// PAINEL
title(painel,"A1:H2","Controle financeiro pessoal");
painel.getRange("A3").values=[["Mês analisado"]];painel.getRange("B3").values=[[new Date(Date.UTC(2026,8,1))]];painel.getRange("B3").setNumberFormat("mmmm yyyy");painel.getRange("A3:B3").format={fill:input,font:{color:blue,bold:true},borders:{preset:"outside",style:"thin",color:red}};painel.getRange("B3").dataValidation={rule:{type:"list",formula1:"Renda!$A$5:$A$28"}};
const cards=[
  ["A5:B5","A6:B7","Renda do mês","=SUMIFS(Renda!$E$5:$E$28,Renda!$A$5:$A$28,$B$3)"],
  ["D5:E5","D6:E7","Gasto realizado","=SUMIFS(Lançamentos!$F$12:$F$511,Lançamentos!$A$12:$A$511,\">=\"&$B$3,Lançamentos!$A$12:$A$511,\"<\"&EDATE($B$3,1))+SUMIFS(Carro!$E$10:$E$209,Carro!$A$10:$A$209,\">=\"&$B$3,Carro!$A$10:$A$209,\"<\"&EDATE($B$3,1))"],
  ["G5:H5","G6:H7","Saldo atual","=A6-D6"],
  ["A9:B9","A10:B11","Fixos previstos","=SUMPRODUCT(Fixos!$D$5:$D$204,--(Fixos!$G$5:$G$204=\"Sim\"),--(Fixos!$E$5:$E$204<=EOMONTH($B$3,0)),--(((Fixos!$F$5:$F$204=\"\")+(Fixos!$F$5:$F$204>=$B$3))>0))+IF(OR(Carro!$H$4=\"\",Carro!$F$4=\"\"),0,IF(AND($B$3>=DATE(YEAR(Carro!$H$4),MONTH(Carro!$H$4),1),$B$3<=EDATE(DATE(YEAR(Carro!$H$4),MONTH(Carro!$H$4),1),Carro!$F$4-1)),IF(Carro!$B$5<>\"\",Carro!$B$5,Carro!$F$5),0))"],
  ["D9:E9","D10:E11","Estimativas","=SUMIFS(Estimativas!$D$5:$D$304,Estimativas!$A$5:$A$304,$B$3)+IF(Carro!$D$5=\"\",0,Carro!$D$5)"],
  ["G9:H9","G10:H11","Sugestão para investir","=IF(A6=0,\"\",MAX(0,MIN(A6*20%,A6-MAX(D6,A10+D10)-A6*10%)))"]
];
for(const [hr,vr,label,formula] of cards){painel.getRange(hr).merge();painel.getRange(hr.split(":")[0]).values=[[label]];painel.getRange(hr).format={fill:redDark,font:{color:white,bold:true},borders:{preset:"outside",style:"thin",color:redDark}};painel.getRange(vr).merge();painel.getRange(vr.split(":")[0]).formulas=[[formula]];painel.getRange(vr).format={fill:white,font:{color:black,bold:true,size:15},horizontalAlignment:"center",verticalAlignment:"center",borders:{preset:"outside",style:"thin",color:line},numberFormat:money};}
painel.getRange("A13:B13").values=[["Indicador","Resultado"]];head(painel.getRange("A13:B13"));
painel.getRange("A14:A18").values=[["Total planejado"],["Disponível após planejamento"],["Gastos / renda"],["Investimento sugerido (%)"],["Situação do mês"]];
painel.getRange("B14").formulas=[["=A10+D10"]];painel.getRange("B15").formulas=[["=A6-B14"]];painel.getRange("B16").formulas=[["=IF(A6=0,\"\",D6/A6)"]];painel.getRange("B17").formulas=[["=IF(A6=0,\"\",G10/A6)"]];painel.getRange("B18").formulas=[["=IF(A6=0,\"Cadastre sua renda\",IF(D6>A6,\"Gastos acima da renda\",IF(D6>B14,\"Acima do planejado\",\"Dentro do planejado\")))"]];
painel.getRange("B14:B15").setNumberFormat(money);painel.getRange("B16:B17").setNumberFormat(pct);painel.getRange("A14:B18").format.borders={insideHorizontal:{style:"thin",color:"#E5E7EB"}};
painel.getRange("B18").conditionalFormats.add("containsText",{text:"acima",format:{fill:"#FECACA",font:{color:"#991B1B",bold:true}}});painel.getRange("B18").conditionalFormats.add("containsText",{text:"Dentro",format:{fill:"#DCFCE7",font:{color:green,bold:true}}});

// Resumo por categoria
painel.getRange("D13:E13").values=[["Categoria","Gasto realizado"]];head(painel.getRange("D13:E13"));painel.getRange("D14:D26").values=categories.map(x=>[x]);
for(let r=14;r<=26;r++)painel.getRange(`E${r}`).formulas=[[`=SUMIFS(Lançamentos!$F$12:$F$511,Lançamentos!$C$12:$C$511,D${r},Lançamentos!$A$12:$A$511,\">=\"&$B$3,Lançamentos!$A$12:$A$511,\"<\"&EDATE($B$3,1))`]];
painel.getRange("D27").values=[["Carro"]];painel.getRange("E27").formulas=[["=SUMIFS(Carro!$E$10:$E$209,Carro!$A$10:$A$209,\">=\"&$B$3,Carro!$A$10:$A$209,\"<\"&EDATE($B$3,1))"]];
painel.getRange("E14:E27").setNumberFormat(money);painel.getRange("D14:E27").format.borders={insideHorizontal:{style:"thin",color:"#E5E7EB"}};

// Histórico mensal para gráfico
painel.getRange("A29:D29").values=[["Mês","Renda","Gasto real","Planejado"]];head(painel.getRange("A29:D29"));
for(let i=0;i<24;i++){const r=30+i,src=5+i;painel.getRange(`A${r}`).formulas=[[`=TEXT(Renda!A${src},\"mmm-yy\")`]];painel.getRange(`B${r}`).formulas=[[`=Renda!E${src}`]];painel.getRange(`C${r}`).formulas=[[`=SUMIFS(Lançamentos!$F$12:$F$511,Lançamentos!$A$12:$A$511,\">=\"&Renda!A${src},Lançamentos!$A$12:$A$511,\"<\"&EDATE(Renda!A${src},1))+SUMIFS(Carro!$E$10:$E$209,Carro!$A$10:$A$209,\">=\"&Renda!A${src},Carro!$A$10:$A$209,\"<\"&EDATE(Renda!A${src},1))`]];painel.getRange(`D${r}`).formulas=[[`=SUMPRODUCT(Fixos!$D$5:$D$204,--(Fixos!$G$5:$G$204=\"Sim\"),--(Fixos!$E$5:$E$204<=EOMONTH(Renda!A${src},0)),--(((Fixos!$F$5:$F$204=\"\")+(Fixos!$F$5:$F$204>=Renda!A${src}))>0))+SUMIFS(Estimativas!$D$5:$D$304,Estimativas!$A$5:$A$304,Renda!A${src})+IF(Carro!$D$5=\"\",0,Carro!$D$5)+IF(OR(Carro!$H$4=\"\",Carro!$F$4=\"\"),0,IF(AND(Renda!A${src}>=DATE(YEAR(Carro!$H$4),MONTH(Carro!$H$4),1),Renda!A${src}<=EDATE(DATE(YEAR(Carro!$H$4),MONTH(Carro!$H$4),1),Carro!$F$4-1)),IF(Carro!$B$5<>\"\",Carro!$B$5,Carro!$F$5),0))`]];}
painel.getRange("B30:D53").setNumberFormat(money);
const catChart=painel.charts.add("bar",painel.getRange("D13:E27"),"Auto");catChart.title.text="Gastos por categoria";catChart.setPosition(painel.getRange("G13:M27"));catChart.width=500;catChart.height=285;catChart.hasLegend=false;if(catChart.series.items[0])catChart.series.items[0].fill={type:"solid",color:red};
const trend=painel.charts.add("line",painel.getRange("A29:D53"),"Auto");trend.title.text="Renda, gastos e planejamento";trend.setPosition(painel.getRange("F30:M48"));trend.width=620;trend.height=315;trend.hasLegend=true;trend.legend.position="top";
if(trend.series.items[0])trend.series.items[0].line={fill:green,style:"solid",width:2};if(trend.series.items[1])trend.series.items[1].line={fill:red,style:"solid",width:2};if(trend.series.items[2])trend.series.items[2].line={fill:gray,style:"dashed",width:2};
painel.getRange("A:A").format.columnWidth=29;painel.getRange("B:B").format.columnWidth=22;painel.getRange("C:C").format.columnWidth=17;painel.getRange("D:D").format.columnWidth=24;painel.getRange("E:E").format.columnWidth=20;painel.getRange("F:F").format.columnWidth=3;painel.getRange("G:H").format.columnWidth=22;painel.freezePanes.freezeRows(3);

// Teste descartável: comprova que renda, planejamento, parcela e gasolina atualizam o painel.
entrada.getRange("B15").values=[[5000]];
fixos.getRange("A5:G5").values=[["Aluguel","Moradia","Pix",1500,new Date(Date.UTC(2026,0,1)),null,"Sim"]];
estim.getRange("A5:D5").values=[[new Date(Date.UTC(2026,8,1)),"Mercado","Mercado",600]];
entrada.getRange("I7").values=[[30000]];entrada.getRange("I9").values=[[24]];entrada.getRange("I11").values=[[new Date(Date.UTC(2026,8,1))]];entrada.getRange("I13").values=[[1500]];entrada.getRange("I15").values=[[500]];
carro.getRange("A10:E11").values=[[new Date(Date.UTC(2026,8,5)),"Parcela do carro","Pix","Parcela de setembro",1500],[new Date(Date.UTC(2026,8,10)),"Gasolina","Crédito","Abastecimento",300]];
wb.recalculate();
console.log((await wb.inspect({kind:"table",range:"Painel!A5:H18",include:"values,formulas",tableMaxRows:20,tableMaxCols:8,maxChars:7000})).ndjson);
entrada.getRange("B15").clear({applyTo:"contents"});
fixos.getRange("A5:G5").clear({applyTo:"contents"});
estim.getRange("A5:D5").clear({applyTo:"contents"});
entrada.getRange("I7").clear({applyTo:"contents"});entrada.getRange("I9").clear({applyTo:"contents"});entrada.getRange("I11").clear({applyTo:"contents"});entrada.getRange("I13").clear({applyTo:"contents"});entrada.getRange("I15").clear({applyTo:"contents"});carro.getRange("A10:E11").clear({applyTo:"contents"});
wb.recalculate();
console.log((await wb.inspect({kind:"table",range:"Painel!A1:H18",include:"values,formulas",tableMaxRows:20,tableMaxCols:8,maxChars:9000})).ndjson);
console.log((await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:300},summary:"formula errors"})).ndjson);
const outDir=path.join(projectRoot,"build");await fs.mkdir(outDir,{recursive:true});
for(const [s,r,n] of [["Controle","A1:P56","controle"],["Preencha aqui","A1:J30","preencha_aqui"],["Painel","A1:M53","painel"],["Carro","A1:N52","carro"],["Lançamentos","A1:J18","lancamentos"],["Renda","A1:E18","renda"],["Fixos","A1:G16","fixos"],["Estimativas","A1:D16","estimativas"]]){const img=await wb.render({sheetName:s,range:r,scale:1.2,format:"png"});await fs.writeFile(`${outDir}/${n}_v2.png`,new Uint8Array(await img.arrayBuffer()));}
const out=await SpreadsheetFile.exportXlsx(wb);await out.save(`${outDir}/Controle_Gastos_Automatico.xlsx`);
