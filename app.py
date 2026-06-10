from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
import requests
import re
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'

# Configuração adaptada para o Postgres do Render ou SQLite local como fallback
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'crm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Controle de sorteio diário
class ControleDiario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_sorteio = db.Column(db.String(10), unique=True) # Formato 'YYYY-MM-DD'
    ids_empresas = db.Column(db.Text) # Armazena os IDs separados por vírgula

# Modelo do Banco de Dados para as Empresas
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
    hoje = datetime.now().strftime('%Y-%m-%d')
    controle = ControleDiario.query.filter_by(data_sorteio=hoje).first()
    
    # Busca todas as empresas que já foram processadas (Histórico)
    historico = Empresa.query.filter(Empresa.status != 'Pendente').all()
    
    empresas_do_dia = []
    
    if controle:
        # Se já houve sorteio hoje, recupera as empresas pelos IDs salvos
        if controle.ids_empresas:
            ids = [int(x) for x in controle.ids_empresas.split(',') if x]
            # Mantém apenas as que continuam 'Pendentes' (caso alguma tenha sido atualizada hoje)
            empresas_do_dia = Empresa.query.filter(Empresa.id.in_(ids), Empresa.status == 'Pendente').all()
    else:
        # Primeiro acesso do dia: sorteia 50 empresas que estão 'Pendentes'
        empresas_pendentes = Empresa.query.filter_by(status='Pendente').all()
        if empresas_pendentes:
            quantidade = min(20, len(empresas_pendentes))
            sorteadas = random.sample(empresas_pendentes, quantidade)
            empresas_do_dia = sorteadas
            
            # Salva a lista de IDs para travar o sorteio de hoje
            string_ids = ','.join([str(e.id) for e in sorteadas])
            novo_controle = ControleDiario(data_sorteio=hoje, ids_empresas=string_ids)
            db.session.add(novo_controle)
            db.session.commit()

    return render_template('dashboard.html', empresas=empresas_do_dia, historico=historico)

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
        else:
            flash('Apenas CNPJ pode ser consultado na Receita automaticamente.')
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'planilha' not in request.files: return redirect(url_for('dashboard'))
    file = request.files['planilha']
    if file.filename == '': return redirect(url_for('dashboard'))

    filepath = os.path.join(file.filename)
    file.save(filepath)

    df = pd.read_excel(filepath)
    novos_registros = 0
    
    for _, row in df.iterrows():
        nome_empresa = row.get('Nome / Nome Empresarial')
        if pd.isna(nome_empresa) or Empresa.query.filter_by(nome=nome_empresa).first():
            continue

        documento = str(row.get('CNPJ / CPF', '')).strip()
        divida_valor = str(row.get('Valor do débito', '0'))

        nova_empresa = Empresa(
            nome=nome_empresa,
            cnpj_cpf=documento,
            divida=divida_valor
        )
        db.session.add(nova_empresa)
        novos_registros += 1
    
    db.session.commit()
    flash(f'✅ {novos_registros} novas empresas importadas para a base de dados!')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run()
