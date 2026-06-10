from flask import Flask, render_template, request, redirect, url_for, flash
import os
import pandas as pd
import requests
import time
import re

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

app.config['UPLOAD_FOLDER'] = 'uploads_temp'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

USUARIO_TESTE = {'email': 'contato@orsiadvogados.com', 'senha': '123'}

# Lista que guarda os contatos
DEVEDORES_PROCESSADOS = []

def calcular_digitos_cnpj(base_12_digitos):
    if len(base_12_digitos) != 12: return base_12_digitos
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(int(base_12_digitos[i]) * pesos1[i] for i in range(12))
    resto1 = soma1 % 11
    digito1 = 0 if resto1 < 2 else 11 - resto1
    base_com_digito1 = base_12_digitos + str(digito1)
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma2 = sum(int(base_com_digito1[i]) * pesos2[i] for i in range(13))
    resto2 = soma2 % 11
    digito2 = 0 if resto2 < 2 else 11 - resto2
    return base_com_digito1 + str(digito2)

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/autenticar', methods=['POST'])
def autenticar():
    if request.form['email'] == USUARIO_TESTE['email'] and request.form['senha'] == USUARIO_TESTE['senha']:
        return redirect(url_for('dashboard'))
    flash('E-mail ou senha incorretos. Tente novamente.')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', empresas=DEVEDORES_PROCESSADOS)

# --- NOVA ROTA: Atualiza o status quando você clica no botão ---
@app.route('/atualizar/<int:empresa_id>/<novo_status>')
def atualizar_status(empresa_id, novo_status):
    global DEVEDORES_PROCESSADOS
    for empresa in DEVEDORES_PROCESSADOS:
        if empresa['id'] == empresa_id:
            if novo_status == 'reuniao':
                empresa['status'] = 'Reunião Agendada'
            elif novo_status == 'retornar':
                empresa['status'] = 'Retornar'
            elif novo_status == 'negado':
                empresa['status'] = 'Sem Interesse'
            break
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'planilha' not in request.files:
        flash('Nenhum arquivo enviado.')
        return redirect(url_for('dashboard'))
    
    file = request.files['planilha']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.')
        return redirect(url_for('dashboard'))

    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        df = pd.read_excel(filepath, nrows=5)
        
        global DEVEDORES_PROCESSADOS
        DEVEDORES_PROCESSADOS = []
        contador_id = 1 # Cria um ID único para cada empresa

        for index, row in df.iterrows():
            documento = str(row['CNPJ / CPF']).strip()
            doc_limpo = re.sub(r'\D', '', documento)
            nome_empresa = row['Nome / Nome Empresarial']
            valor_debito = row['Valor do débito']

            try:
                valor_formatado = f"{float(valor_debito):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except:
                valor_formatado = "N/A"

            if len(doc_limpo) <= 8:
                raiz = doc_limpo.zfill(8)
                cnpj_completo = calcular_digitos_cnpj(raiz + "0001")
            elif len(doc_limpo) < 14:
                cnpj_completo = doc_limpo.zfill(14)
            else:
                cnpj_completo = doc_limpo

            telefone = "Não encontrado"
            
            if len(cnpj_completo) == 14:
                try:
                    resposta = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_completo}", timeout=10)
                    if resposta.status_code == 200:
                        telefone = resposta.json().get('ddd_telefone_1', 'Não cadastrado')
                except:
                    telefone = "Erro de conexão"
                time.sleep(1)

            # Salva a empresa com o ID e o Status Pendente
            DEVEDORES_PROCESSADOS.append({
                'id': contador_id,
                'nome': nome_empresa,
                'telefone': telefone,
                'divida': valor_formatado,
                'status': 'Pendente'
            })
            contador_id += 1

        flash('✅ Planilha processada! (Mostrando as 5 primeiras linhas como teste).')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
