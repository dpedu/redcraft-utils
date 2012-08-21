#! /usr/bin/env python

import threading
import operator
from socket import *
import json
import MySQLdb
import os

class InfoThread(threading.Thread):
	def __init__(self, socket):
		threading.Thread.__init__(self)
		self.socket = socket[0]
		self.start()
	def run(self):
		# Fetch memory statistics
		memStats = {}
		mem = open("/proc/meminfo", "r")
		while True:
			line = mem.readline()
			if line=="":
				break
			if "MemTotal" in line or "MemFree" in line:
				while line.find("  ")>=0:
					line = line.replace("  ", " ")
				line = line.split(" ")
				memStats[line[0]]=int(line[1])
		mem.close()
		
		conn = MySQLdb.connect (host = "sqlhost", user = "sqluser", passwd = "sqlpasswd", db = "sqldb")
		
		# Find Richest players
		richplayers = []
		cursor = conn.cursor(MySQLdb.cursors.DictCursor)
		cursor.execute("SELECT * FROM `iConomy` ORDER BY `balance` DESC LIMIT 100");
		while True:
			row = cursor.fetchone()
			if row==None or len(richplayers)>=25:
				break
			if not "-" in row["username"] and row["username"] not in ['admin1', 'admin2']:
				richplayers.append({"user":row["username"], "balance":row["balance"]})
		memStats["richPlayers"]=richplayers
		
		# Find most edits
		cursor.execute("SELECT topq.sum, plr.playername FROM (SELECT playerid, COUNT( * ) AS  `sum` FROM  `lb-world` GROUP BY  `playerid` ORDER BY `sum` DESC) as `topq` INNER JOIN `lb-players` as `plr` ON `plr`.`playerid` = `topq`.playerid WHERE plr.playername!='TNT' AND plr.playername!='WaterFlow' AND plr.playername!='LavaFlow' AND plr.playername!='LeavesDecay' and plr.playername!='NaturalGrow' LIMIT 25");
		editingPlayers = []
		while True:
			row = cursor.fetchone()
			if row==None:
				break
			editingPlayers.append({"username":row["playername"], "total":row["sum"]})
		# Find richest towns
		richTowns = []
		cursor.execute("SELECT * FROM `iConomy` WHERE `username` LIKE 'town-%' AND username!='town-zeal' ORDER BY `balance` DESC LIMIT 25")
		while(True):
			row = cursor.fetchone();
			if row==None:
				break
			richTowns.append({"town":row["username"].replace("town-", ""), "balance":row["balance"]})
		memStats["richTowns"]=richTowns
		memStats["editingPlayers"]=editingPlayers
		# Find largest towns
		cursor.execute('SELECT COUNT(*) as `count`, `town`  FROM `TOWNY_RESIDENTS` WHERE `town`!="" GROUP BY `town` ORDER BY `count` DESC ;');
		largest_towns = []
		while True:
			row = cursor.fetchone();
			if row == None or len(largest_towns)>=25:
				break;
			largest_towns.append({"town":row["town"], "residents":row["count"]});
		memStats["largestTowns"]=largest_towns
		conn.close ()
		self.socket.send(json.dumps(memStats))
		self.socket.close()
	
mainsocket = socket( AF_INET,SOCK_STREAM)
mainsocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
mainsocket.bind(("0.0.0.0", 1234))
mainsocket.listen(9999)
while True:
	s = mainsocket.accept();
	x = InfoThread(s);
