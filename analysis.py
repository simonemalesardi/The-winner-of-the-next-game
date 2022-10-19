import pandas as pd
import numpy as np 
from tqdm import tqdm
from team import Team
from datetime import datetime
import time
from sklearn.model_selection import train_test_split
from ranking import Ranking

class MatchAnalysis:
    rename_fields = {
        'Squadra': 'team1',
        'Avversario': 'team2',
        'Data': 'date',
        'Stadio': 'stadium',
        'Girone': 'matchday',
        'Risultato': 'result',
        'Rf': 'goals',
        'Tiri': 'total_shots',
        'Tiri.1': 'shots_on_target',
        'Rigori': 'goals_on_penalty',
        'Rig T': 'total_penalties',
        'Compl': 'completed_passings',
        'Tent': 'total_passings',
        'Angoli': 'corners',
        'Poss.': 'percentage_possession',
        'Falli': 'fouls',
        'Amm.': 'yellow_cards',
        'Esp.': 'red_cards',
    }

    def __init__(self, path):
        self.read_matches(path)
        self.create_team_dataset()
        self.ranking = None

    def read_matches(self, path):
        self.matches_fe_team = pd.read_csv(path, index_col=0)
        self.matches_fe_team.reset_index(drop=True, inplace=True)

    def create_team_dataset(self):
        #per ogni squadra nel campionato viene creato un dataset che contiene tutte le partite giocate dalla squadra con le relative statistiche
        self.matches_by_team = []
        for number, team in enumerate(sorted(self.matches_fe_team.team1.unique())):
            self.matches_by_team.append(Team(number, team, self.matches_fe_team[self.matches_fe_team.team1 == team]))

    def divide_and_merge_home_away(self):
        #dato che il dataset scaricato contiene le informazioni relative alle statistiche delle squadre, ci saranno per ogni partita 2 record che si riferiscono alla stessa partita: un record per la squadra di casa e uno per la squadra di trasferta. Divido quindi chi gioca in casa da chi gioca in trasferta andando a considerare il campo "Stadio" che dice appunto se la squadra gioca in casa o in trasferta (la squadra presa di riferimento è quella su cui vengono prese le statistiche). Successivamente i 2 record che si riferiscono alla stessa partita (uno nel dataset home_games, uno nel dataset away_games) vengono combinati ed alla fine ottengo un dataset 
        home_games = self.matches_fe_team[self.matches_fe_team.stadium =='Casa']
        away_games = self.matches_fe_team[self.matches_fe_team.stadium =='Ospiti']
        
        self.getDiff_home_away(home_games, away_games)

    def getDiff_home_away(self, hm, am):
        self.diff_dataset = []
        for index, home_match in hm.iterrows():
            away_match = am[(am['date'] == home_match['date']) & (am['team2'] == home_match['team1']) & (am['team1'] == home_match['team2'])]
            away_match_reduced = away_match.drop(columns = ['date', 'team1', 'team2', 'stadium', 'matchday', 'result'])
            for col in away_match_reduced.columns:
                home_match[col] = home_match[col] - away_match_reduced[col].values[0]

            self.diff_dataset.append(home_match)

        self.diff_dataset = pd.DataFrame(self.diff_dataset)
        
        self.diff_dataset.drop(columns=['stadium', 'matchday'], inplace=True)
        self.diff_dataset.sort_values(by=["date"], inplace=True)
        self.diff_dataset.reset_index(drop=True, inplace=True)

        self.diff_dataset.rename(columns={'team1':'home', 'team2': 'away'}, inplace=True)
        self.diff_dataset.to_csv("diff_matches.csv")

    def readDiff_home_away(self):
        self.diff_dataset = pd.read_csv("files/diff_matches.csv", index_col=0)

    def get_dummies(self):
        stacked = self.diff_dataset[['home', 'away']].stack()
        index = stacked.index.get_level_values(0)
        result = pd.crosstab(index=index, columns=stacked)
        result.index.name = None
        result.columns.name = None

        dummy_match = pd.get_dummies(self.diff_dataset
                ,columns = ['home']
                ,prefix = ['h']
                )

        dummy_match = dummy_match.drop(['away'], axis=1)
        pos = 0
        for col in result.columns:
            dummy_match.insert(pos, col, result[col])
            pos += 1

        self.diff_dataset = dummy_match
 
    def reduce_dataset(self, date): 
        #creo il dataset per il modello di ML
        limit_date = datetime.strptime(date, '%Y-%m-%d')
        #matches = aa.matches_fe_team[a.matches_fe_team.date <= limit_date]
        self.matches_fe_team['date'] = pd.to_datetime(self.matches_fe_team['date'], format='%Y-%m-%d') #devo convertire la data altrimenti non posso controllare quando una data è minore
        self.matches_fe_team = self.matches_fe_team[self.matches_fe_team.date < limit_date] 
        self.divide_and_merge_home_away()

    def split_and_set_avg(self, avg_all_ds, number):
        #devo convertire il tipo delle colonne perché la media tra i valori mi dà un numero con la virgola (da int a float)
        float_features_and_avg = [x for x in self.diff_dataset.columns if x != 'home' and x != 'away' and x != 'date' and x != 'result' and x != 'rank_h' and x != 'rank_a']
        self.diff_dataset[float_features_and_avg] = self.diff_dataset[float_features_and_avg].astype(float)
        
        #se avg_all_ds è true significa che calcolo la media di tutti i match precedenti per tutto il dataset (X <= 0) o per una parte (X>0) e poi lo splitto in train e test. Se è false semplicemente calcolo le medie solo per il test
        if avg_all_ds:
            self.calculate_avg_all(float_features_and_avg, number)

        """"
        #shuffle viene settato a False perché non voglio che vengano randomizzate le partite, verrebbe un risultato sballato
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(X, y, test_size=0.2, shuffle=False) 

        if avg_all_ds:
            self.set_codes()
        else:
            #calcolo la media solo per il test set
            self.calculate_avg(float_features_and_avg, number)
        """

    def merge_(self):
        self.features = [x for x in self.diff_dataset.columns if x != 'result']

        X, y = self.diff_dataset[self.features], self.diff_dataset.result.values
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(X, y, test_size=0.2, shuffle=False) 

        self.set_codes()

    def calculate_avg(self, avg_features, number):
        for i, match_value in self.X_test.iterrows():
            home, away = match_value.home, match_value.away
            #calcolo la media dei match dei due dataset delle squadre coinvolte nel match
            if number > 0:
                averages_home, change = self.get_team_by_name(home).get_avg_last_X_matches(number, match_value.date, avg_features)
                averages_away, change = self.get_team_by_name(away).get_avg_last_X_matches(number, match_value.date, avg_features)
            else:
                averages_home, change = self.get_team_by_name(home).get_avg_all_matches(match_value.date, avg_features)
                averages_away, change = self.get_team_by_name(away).get_avg_all_matches(match_value.date, avg_features)

            for col in avg_features: 
                diff = averages_home[col] - averages_away[col]
                self.X_test.at[i, col] = diff


        for i, match_value in self.X_train.iterrows():
            self.X_train.at[i, 'home'] = self.get_team_code(match_value.home)
            self.X_train.at[i, 'away'] = self.get_team_code(match_value.away)
        
        for i, match_value in self.X_test.iterrows():
            self.X_test.at[i, 'home'] = self.get_team_code(match_value.home)
            self.X_test.at[i, 'away'] = self.get_team_code(match_value.away)

        self.X_train = self.X_train.drop(columns=['date'])
        self.X_test = self.X_test.drop(columns=['date'])
        
    def set_ranking(self, ranking):
        self.ranking = ranking

    def calculate_avg_all(self, avg_features, X):
        #calcola la media nei record del test set
        for i, match_value in self.diff_dataset.iterrows():
            home, away = match_value.home, match_value.away
            #calcolo la media dei match dei due dataset delle squadre coinvolte nel match
            if X > 0:
                #MEDIA ULTIMI X MATCH
                averages_home, change = self.get_team_by_name(home).get_avg_last_X_matches(X, match_value.date, avg_features)
                averages_away, change = self.get_team_by_name(away).get_avg_last_X_matches(X, match_value.date, avg_features)
            else:
                #MEDIA TUTTI MATCH
                averages_home, change = self.get_team_by_name(home).get_avg_all_matches(match_value.date, avg_features)
                averages_away, change = self.get_team_by_name(away).get_avg_all_matches(match_value.date, avg_features)           

            #dataset in posizione i alla colonna rank_H ci va il rank home, mentre alla colonna rank_A ci va il rank away
            if self.ranking != None:
                self.get_ranks(i, home, away, match_value.date)

            if change: 
                for col in avg_features: 
                    diff = averages_home[col] - averages_away[col]
                    self.diff_dataset.at[i, col] = diff

        self.diff_dataset.to_csv('diff_with_ranking.csv')

    def get_ranks(self, pos, home, away, date):
        #ottengo il rank delle squadre e controllo se le due squadre hanno già giocato nel campionato
        #se si sono affrontate devo considerare anche quella partita nel calcolo
        rank_h, rank_a = self.ranking.get_rank(home, away)
        
        if self.get_team_by_name(home).get_previous(away, date):
            rank_h += 1
        if self.get_team_by_name(away).get_previous(home, date):
            rank_a += 1
        
        self.diff_dataset.at[pos, 'rank_h'] = rank_h
        self.diff_dataset.at[pos, 'rank_a'] = rank_a

    def set_codes(self):
        for i, match_value in self.X_train.iterrows():
            self.X_train.at[i, 'home'] = self.get_team_code(match_value.home)
            self.X_train.at[i, 'away'] = self.get_team_code(match_value.away)
        
        for i, match_value in self.X_test.iterrows():
            self.X_test.at[i, 'home'] = self.get_team_code(match_value.home)
            self.X_test.at[i, 'away'] = self.get_team_code(match_value.away)

        self.X_train = self.X_train.drop(columns=['date'])
        self.X_test = self.X_test.drop(columns=['date'])

    def get_team_code(self, name): 
        for team in self.matches_by_team:
            if team.name == name:
                return team.id
    
    def get_name_by_id(self, id): 
        for team in self.matches_by_team:
            if team.id == id:
                return team.name
              
    def get_team_by_name(self, name):
        for team in self.matches_by_team:
            if team.name == name:
                return team