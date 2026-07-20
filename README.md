# Facturier Automatique — Django MVT (SQLite, HTML/CSS)

Version 100% Django "classique" (Model-View-Template) : **pas de React, pas
d'API séparée**. Toutes les pages sont rendues côté serveur avec les
templates Django, la base de données est **SQLite** (un simple fichier,
aucun serveur à installer), et l'authentification utilise les sessions
Django natives.

Reprend toutes les fonctionnalités de la version précédente (React + API) :
multi-entreprises, réduction, cadeaux, paiements combinés (dont Orange
Money / MTN Money / Moov Money), facture A5 en français en F CFA, session
de caisse avec fermeture automatique, historique filtrable, réinitialisation
de mot de passe — **plus l'import de produits depuis un fichier Excel**.

## Démarrage rapide

```bash
python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations core
python manage.py migrate
python manage.py seed             # crée un compte admin par défaut
python manage.py runserver        # démarre l'application sur http://localhost:8000
```

Identifiants créés par `seed` :
- Téléphone : `0000000000`
- Mot de passe : `Admin@1234`

Connectez-vous puis créez votre première **entreprise**, puis vos
**vendeurs**, puis vos **produits** (manuellement ou en les important
depuis Excel).

Aucune installation Node/npm n'est nécessaire : tout est servi par Django
(HTML, CSS, et un tout petit peu de JavaScript vanilla, voir plus bas).

## Import de produits depuis Excel

Page **Base Produits → Importer depuis Excel** (`/produits/importer/`) :
1. Téléchargez le modèle Excel (bouton "Télécharger le modèle Excel") pour
   avoir les bonnes colonnes : *Désignation, Description, Prix (F CFA),
   Stock, Seuil critique*.
2. Remplissez le fichier (une ligne par produit, la première ligne
   d'en-tête est ignorée à l'import).
3. Importez-le : chaque ligne valide crée un nouveau produit dans
   l'entreprise active ; les lignes invalides (prix manquant/incorrect...)
   sont listées sans bloquer l'import des autres lignes.

Implémenté avec `openpyxl` (lecture et génération de fichiers `.xlsx`),
voir `core/product_import.py`.

## Structure du projet

```
facturier_mvt/
├── manage.py
├── requirements.txt
├── facturier_mvt/            # configuration du projet (settings, urls)
└── core/                     # application principale
    ├── models.py             # Company, User, Product, Sale, SalePayment, CashSession, SaleItem
    ├── forms.py               # tous les formulaires (connexion, produits, import Excel, caisse...)
    ├── views.py               # toutes les vues (une par page)
    ├── urls.py
    ├── decorators.py          # admin_required, seller_required
    ├── helpers.py             # résolution de l'entreprise active
    ├── context_processors.py  # injecte l'entreprise active dans tous les templates
    ├── invoice_pdf.py         # génération PDF (ReportLab, format A5)
    ├── product_import.py      # import/modèle Excel (openpyxl)
    ├── management/commands/seed.py
    ├── templates/core/        # tous les templates HTML
    └── static/core/
        ├── css/styles.css     # feuille de style (thème bleu/noir, responsive, impression A5)
        └── js/app.js          # JS minimal (voir ci-dessous)
```

## Rôles

| Rôle    | Portée                                                                 |
|---------|--------------------------------------------------------------------------|
| ADMIN   | Global : Dashboard, Base Produits (+ import Excel), Entreprises, Vendeurs, Historique, Caisse. Sélecteur d'entreprise active dans la Navbar. |
| SELLER  | Rattaché à UNE entreprise : Caisse (avec session d'ouverture/fermeture) et son propre historique de ventes. |

## Le "panier" de la Caisse

Contrairement à la version React (état en mémoire du navigateur), le
panier est ici stocké dans la **session Django** (`request.session["cart"]`)
: chaque ajout/retrait de produit est une requête POST classique qui
recharge la page. C'est le fonctionnement natural d'une application MVT
server-rendered.

## Un peu de JavaScript, et pourquoi

Le cahier des charges demande "HTML et CSS" ; la quasi-totalité de
l'application (navigation, formulaires, panier, filtres, CRUD) fonctionne
sans une ligne de JavaScript, uniquement avec des formulaires et des liens.
Deux comportements restent toutefois difficiles à obtenir en pur HTML/CSS,
et utilisent un peu de JavaScript vanilla (`core/static/core/js/app.js`,
~30 lignes, aucune dépendance) :

1. **Filtre produit "en direct" à la Caisse** : les lignes du tableau déjà
   affiché sont montrées/masquées au fur et à mesure de la saisie, sans
   recharger la page.
2. **Déconnexion automatique** à l'échéance de la session de caisse : un
   minuteur vérifie toutes les 15 secondes l'heure de fermeture prévue et
   soumet un formulaire de fermeture quand elle est atteinte.

Le menu mobile (bouton "trois traits") est lui réalisé en **CSS pur**
(technique de la case à cocher cachée), sans JavaScript.

## Sécurité

- Mots de passe hachés nativement par Django (PBKDF2).
- Authentification par sessions Django (cookies signés), protection CSRF
  native sur tous les formulaires.
- Décorateurs `admin_required` / `seller_required` sur chaque vue sensible.
- Décrémentation du stock dans une transaction (`transaction.atomic` +
  `select_for_update`) pour la cohérence en cas de ventes concurrentes.
- Import Excel : le fichier est entièrement validé ligne par ligne avant
  toute écriture en base ; aucune ligne invalide n'est importée
  silencieusement (elle est listée comme erreur).

## Limites connues

- Le tableau des articles sur la facture A5 n'est pas paginé (adapté à un
  usage boutique/comptoir avec quelques articles par facture).
- SQLite convient très bien à un usage mono-serveur / petite structure ;
  pour une charge plus importante ou plusieurs serveurs en parallèle,
  basculer vers PostgreSQL reste possible en ne changeant que le bloc
  `DATABASES` de `settings.py` (le reste du code est indépendant du moteur
  de base de données).
