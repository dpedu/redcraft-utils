#!/usr/bin/env python

import subprocess
import os
import re
import sys
import threading
import time
import random
import urllib2
import re
import yaml

# Main class
class MinecraftServerRunner(threading.Thread):
	def __init__(self, configFile):
		threading.Thread.__init__(self)
		
		# Config path - configuration yml saved to self.config
		self.configFile = configFile
		self.reloadConfig()
		
		# currently running server object
		self.server = None
		
		# should the server be restarted if it exits?
		self.respawn = True
		
		# CMD line input
		self.stdinThread = StdinThread(self)
		
		# Timers for internal functions
		self.timers = {
			"RestartTimer":			None, # restart interval
			"MessageTimer":			threading.Timer(self.config["message_interval"], self.timer_Message), # in-game message interval
			"SaveTimer":			threading.Timer(self.config["save_interval"], self.timer_Save), # auto-save interval
			"RestartCheckTimer":	threading.Timer(1, self.timer_CheckRespawn), # status check task
			"ConfigReloadTimer":	threading.Timer(self.config["config_update_interval"], self.timer_ConfigReload), # config refreshing
		}
		# single point to store data instead of a ton of class properties
		self.data = {
			"LastMessage":0,
			"LastRestart":time.time()
		}
		
		# Start all tmers
		self.timers["RestartCheckTimer"].start()
		self.timers["SaveTimer"].start()
		self.timers["MessageTimer"].start()
		self.timers["ConfigReloadTimer"].start()
	
	def timer_Restart(self):
		" called by timer to restart the server "
		self.server.stopServer()
		#self.server = MinecraftServer(self)
		try:
			self.timers["RestartTimer"].cancel()
		except:
			pass
		self.timers["RestartTimer"] = threading.Timer(self.config["restart_interval"], self.timer_Restart)
		self.timers["RestartTimer"].start()
	
	def timer_Message(self):
		" called by timer to send the next in game message "
		self.data["LastMessage"]+=1
		if self.data["LastMessage"]>=len(self.config["messages"]):
			self.data["LastMessage"]=0
		for line in self.config["messages"][self.data["LastMessage"]]:
			self.server.write("say %s" % line)
		
		self.timers["MessageTimer"] = threading.Timer(self.config["message_interval"], self.timer_Message)
		self.timers["MessageTimer"].start()
	
	def timer_Save(self):
		" called by timer to save-all the map "
		self.server.write("save-all");
		self.timers["SaveTimer"] = threading.Timer(self.config["save_interval"], self.timer_Save)
		self.timers["SaveTimer"].start()
		
	def timer_ConfigReload(self):
		" called by timer to reload config options"
		self.reloadConfig();
		self.timers["ConfigReloadTimer"] = threading.Timer(self.config["config_update_interval"], self.timer_ConfigReload)
		self.timers["ConfigReloadTimer"].start()
	
	def timer_CheckRespawn(self):
		" called every second to check server status "
		loop = True
		if self.server == None:
			self.startServer()
		else:
			if not self.server.isAlive():
				if self.respawn:
					print "\n\n **** Respawning Server\n"
					self.startServer()
				else:
					print "\n\n **** Exiting\n"
					loop = False
					sys.exit(1)
		if loop:
			self.timers["RestartCheckTimer"] = threading.Timer(1, self.timer_CheckRespawn)
			self.timers["RestartCheckTimer"].start()
	
	def killTimers(self):
		" used during exiting "
		for timer in self.timers:
			try:
				self.timers[timer].cancel()
			except:
				pass
	
	def reloadConfig(self):
		" loads config info from file on disk"
		self.config = yaml.load(file(self.configFile, 'r'))
	
	def startServer(self):
		" creates a new server object & starts it"
		self.server = MinecraftServer(self)
		self.timers["RestartTimer"] = threading.Timer(self.config["restart_interval"], self.timer_Restart)
		self.timers["RestartTimer"].start()
	
	def doStop(self):
		" call this to kill the server and exit cleanly "
		print "\n\n **** Exiting Runner "
		self.respawn = False
		self.server.stopServer()
		self.killTimers()
	
	def handleStdinLine(self, line):
		" called by the stdin monitor when a line of STDIN is recieved"
		line = line.strip()
		" called for each stdin line"
		if(line.startswith("!")):
			if(line.startswith("!restart")):
				self.timers["RestartTimer"].cancel()
				self.timers["RestartTimer"] = threading.Timer(30, self.timer_Restart)
				self.timers["RestartTimer"].start()
				self.server.write("say PLANNED RESTART IN 30 SECONDS.")
				self.server.write("say ALL PROGRESS WILL BE SAVED...")
		else:
			self.server.write(line)
	
	def handleServerLine(self, line):
		" called by the server thread whenever an output line is received "
		print line.strip()
		
		if "logged in with entity id" in line:
			newPname = line.split("[INFO] ")[1].split(" [/")[0];
		elif "[INFO] CONSOLE: Save complete." in line:
			self.server.write("say SAVE COMPLETE!");
		elif "!next_restart" in line:
			timenext = str(int((self.calcNextRestart()/60.0)*10.0)/10.0)
			sself.server.write("say Next restart in %s minutes." % timenext)
	def calcNextRestart(self):
		return (self.config["restart_interval"]-(time.time()-self.data["LastRestart"]))

class MinecraftServer(threading.Thread):
	" object spawned per server instance "
	def __init__(self, master):
		threading.Thread.__init__(self)
		self.master = master
		self.server = None
		self.start()
	def run(self):
		" runs the server and remains in this method until it exits "
		args = (
			self.master.config["javapath"],
			"-Xms%s" % self.master.config["memory"],
			"-Xmx%s" % self.master.config["memory"],
			"-Djline.terminal=jline.UnsupportedTerminal",
			"-jar",
			self.master.config["jar"],
			"-nojline"
		)
		print args
		self.server = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE);
		
		while self.master.respawn:
			try:
				output = self.server.stderr.readline()
				if output == "":
					break
				handle = self.master.handleServerLine(output);
			except:
				pass
	def write(self, text):
		" sends a line of text to the server "
		self.server.stdin.write(text+"\n")
	def stopServer(self): 
		" stop the server, and save "
		self.write("kickall Server is restarting - Please Reconnect.");
		self.write("save-all")
		self.write("stop")
		while self.isAlive():
			time.sleep(.5)
		print " **** Server has stopped."
	def isAlive(self):
		" returns true if the java process is still alive "
		return self.server.poll() == None

class StdinThread(threading.Thread):
	" for reading STDIN and passing it to the java process "
	def __init__(self, master):
		threading.Thread.__init__(self)
		self.master = master
		self.start()
	def run(self):
		while self.master.respawn:
			try:
				line = sys.stdin.readline()
				if line:
					self.master.handleStdinLine(line)
				time.sleep(0.1);
			except:
				pass

if __name__ == '__main__':
	runner = MinecraftServerRunner("runner.yml")
	
	try: 
		while True:
			time.sleep(10000)
	except KeyboardInterrupt: 
		runner.doStop()
