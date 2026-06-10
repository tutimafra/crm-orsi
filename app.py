from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
import requests
import re
import random
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'crm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Controle de sorteio por tempo (Expira a cada 10 minutos)
class ControleTempo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    horario_validade = db.Column(db.DateTime) # Momento em que o lote atual expira
    ids_empresas = db.Column(db.Text)

class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(250))
    cnpj_cpf = db.Column(db.String(50))
    telefone = db.Column(db.String(50), default='Clique em Buscar')
    email = db.Column(db.String(100), default='Clique em Buscar')
    divida = db.Column(db.String(50))
    status = db.Column(db.String(50), default='Pendente')

with app.app_context():
    db.create_all()

@app.route('/')
def login(): 
    return render_template('login.html')

@app.route('/autenticar', methods=['POST'])
def autenticar():
    email_digitado = request.form.get('email', '').strip()
    senha_digitada = request.form.get('senha', '').strip()
    if email_digitado == 'contato@exemplo.com.br' and senha_digitada == '123':
        return redirect(url_for('dashboard'))
    flash('E-mail ou senha incorretos. Tente novamente.')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    agora = datetime.now()
    controle = ControleTempo.query.order_by(ControleTempo.id.desc()).first()
    
    historico = Empresa.query.filter(Empresa.status != 'Pendente').all()
    empresas_do_lote = []
    
    # Verifica se o lote atual ainda é válido
    if controle and controle.horario_validade > agora:
        if controle.ids_empresas:
            ids = [int(x) for x in controle.ids_empresas.split(',') if x]
            # Exibe as empresas do lote que continuam Pendentes
            empresas_do_lote = Empresa.query.filter(Empresa.id.in_(ids), Empresa.status == 'Pendente').all()
    else:
        # Lote expirou ou é o primeiro acesso: Sorteia 5 novas empresas
        empresas_pendentes = Empresa.query.filter_by(status='Pendente').all()
        if empresas_pendentes:
            quantidade = min(5, len(empresas_pendentes))
            sorteadas = random.sample(empresas_pendentes, quantidade)
            empresas_do_lote = sorteadas
            
            # Define validade para daqui a 10 minutos
            validade = agora + timedelta(minutes=10)
            string_ids = ','.join([str(e.id) for e in sorteadas])
            
            novo_controle = ControleTempo(horario_validade=validade, ids_empresas=string_ids)
            db.session.add(novo_controle)
            db.session.commit()

    return render_template('dashboard.html', empresas=empresas_do_lote, historico=historico)

@app.route('/atualizar/<int:id>/<novo_status>')
def atualizar_status(id, novo_status):
    empresa = Empresa.query.get(id)
    if empresa:
        status_map = {'reuniao': 'Reunião Agendada', 'retornar': 'Retornar', 'negado': 'Sem Interesse'}
        empresa.status = status_map.get(novo_status, 'Pendente')
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/buscar_api/<int:id>')
def buscar_api(id):
    empresa = Empresa.query.get(id)
    if empresa and empresa.cnpj_cpf:
        doc_limpo = re.sub(r'\D', '', empresa.cnpj_cpf)
        if len(doc_limpo) == 14:
            try:
                res = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{doc_limpo}", timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    empresa.telefone = data.get('ddd_telefone_1', 'Não cadastrado')
                    empresa.email = data.get('email', 'Não cadastrado')
                    db.session.commit()
                    flash(f'✅ Dados de {empresa.nome} atualizados!')
                else:
                    flash('Empresa não encontrada na Receita.')
            except:
                flash('Erro temporário na API. Tente novamente.')
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'planilha' not in request.files: return redirect(url_for('dashboard'))
    file = request.files['planilha']
    if file.filename == '': return redirect(url_for('dashboard'))

    filepath = os.path.join(file.filename)
    file.save(filepath)

    # Lendo o arquivo (O segredo do CSV está aqui abaixo)
    if file.filename.endswith('.csv'):
        df = pd.read_csv(filepath, encoding='utf-8', sep=';')
    else:
        df = pd.read_excel(filepath)
    
    novas_empresas = []
    nomes_existentes = {e.nome for e in Empresa.query.with_entities(Empresa.nome).all()}
    
    for _, row in df.iterrows():
        nome_empresa = row.get('Nome / Nome Empresarial')
        if pd.isna(nome_empresa) or nome_empresa in nomes_existentes:
            continue

        documento = str(row.get('CNPJ / CPF', '')).strip()
        divida_valor = str(row.get('Valor do débito', '0'))

        nova_empresa = Empresa(
            nome=nome_empresa,
            cnpj_cpf=documento,
            divida=divida_valor
        )
        novas_empresas.append(nova_empresa)
        nomes_existentes.add(nome_empresa)
    
    if novas_empresas:
        db.session.bulk_save_objects(novas_empresas)
        db.session.commit()
        flash(f'✅ {len(novas_empresas)} empresas importadas com sucesso!')
    else:
        flash('Nenhuma nova empresa encontrada.')
        
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run()
