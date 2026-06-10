from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
import requests
import time
import re

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'crm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelo do Banco de Dados
class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200))
    telefone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    divida = db.Column(db.String(50))
    status = db.Column(db.String(50), default='Pendente')

with app.app_context():
    db.create_all()

@app.route('/')
def login(): 
    return render_template('login.html')

@app.route('/autenticar', methods=['POST'])
def autenticar():
    # .strip() remove espaços ocultos involuntários digitados pelo usuário
    email_digitado = request.form.get('email', '').strip()
    senha_digitada = request.form.get('senha', '').strip()
    
    if email_digitado == 'contato@exemplo.com.br' and senha_digitada == '123':
        return redirect(url_for('dashboard'))
    
    # Envia o aviso de erro exato para o seu login.html exibir na tela
    flash('E-mail ou senha incorretos. Tente novamente.')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    empresas = Empresa.query.all()
    return render_template('dashboard.html', empresas=empresas)

@app.route('/atualizar/<int:id>/<novo_status>')
def atualizar_status(id, novo_status):
    empresa = Empresa.query.get(id)
    if empresa:
        status_map = {'reuniao': 'Reunião Agendada', 'retornar': 'Retornar', 'negado': 'Sem Interesse'}
        empresa.status = status_map.get(novo_status, 'Pendente')
        db.session.commit()
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

    filepath = os.path.join(basedir, file.filename)
    file.save(filepath)

    df = pd.read_excel(filepath) # Lê a planilha inteira
    
    for _, row in df.iterrows():
        documento = str(row['CNPJ / CPF']).strip()
        doc_limpo = re.sub(r'\D', '', documento)
        
        # Ignora linhas com nomes vazios ou registros já existentes no banco
        nome_empresa = row['Nome / Nome Empresarial']
        if pd.isna(nome_empresa) or Empresa.query.filter_by(nome=nome_empresa).first():
            continue

        telefone = "Não encontrado"
        email = "Não encontrado"
        
        # Consulta à API caso seja CNPJ válido
        if len(doc_limpo) == 14:
            try:
                res = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{doc_limpo}", timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    telefone = data.get('ddd_telefone_1', 'Não cadastrado')
                    email = data.get('email', 'Não cadastrado')
            except: 
                pass
            time.sleep(1) # Respeita o limite de requisições da API

        nova_empresa = Empresa(
            nome=nome_empresa,
            telefone=telefone,
            email=email,
            divida=str(row['Valor do débito'])
        )
        db.session.add(nova_empresa)
    
    db.session.commit()
    flash('✅ Planilha processada e salva com sucesso!')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run()
