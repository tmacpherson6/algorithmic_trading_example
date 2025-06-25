'''
___________________________________________________________________________________________________________________________________

                                            Example Bot - Version: 0.2.11
                                                Last Revised: 06/25/25

___________________________________________________________________________________________________________________________________

Production: Live Trading Environment

This is the actual trading bot program based on our historical back testing model.
This model is based on an opening range break strategy that is currently based on the following parameters

Timeframe: 5 min candles
Entry: High/Low of 5 min candle
StopLoss: High/Low of 5 min candle
Profit Target: 2x StopLoss


We will be using an OCO order for our buy and sell placement of two bracket orders so that it will limit our
need to monitor the position at all.

Latest Version Updates:
- Made the call to the database more robust because it had been throwing errors leading to issues with running the script repetitively
- Added functionality to cancel open orders on new positions if haven't triggered by 1:30pm
- Address different timestamps from TWS and Gateway (Launch of Live Trading)
- Added a section for dynamic contract sizing
- Fixed minor Order ID bugs
- Algorithm now runs every 3 seconds all day
- Updated to add a single re-entry if we stopped out on the first trade.
- Changed to historical data acquisition from tick data acquisition.
- Removed a maximum stop size of $150 maximum loss (not including slippage) based on back testing results.
- Added a loop to deal with a historical data call that hasn't returned data yet
'''

#-------------------------------------------------------------------------------------------------------------------------------
                                            #IMPORT LIBRARIES AND DEPENDENCIES
#-------------------------------------------------------------------------------------------------------------------------------

import numpy as np
import pandas as pd
import RiverRose as rr
import datetime as dt
import sqlalchemy as sa
import urllib.parse
import threading
import time 
from ibapi.execution import ExecutionFilter

#---------------------------------------------------------------------------------------------------------------------------
                            #Get our current algorithm performance for contract sizing
#---------------------------------------------------------------------------------------------------------------------------
#Indicate our client Id so we can look at executions only by this algo
client_id = input("What is your client ID for this algorithm? ")
client_id = int(client_id)

#Indicate whehter we are trading live money or simulated environemnt
live_or_sim = 'live' #Live or Sim
#Indicate whether we are connecting through Trader Work Station or IB Gateway
TWS_or_gateway = 'gateway' #TWS or Gateway

if live_or_sim.lower() == 'sim':
    account = 1
elif live_or_sim.lower() == 'live':
    account = 2

DB_NAME = input("What is the name of your database: ")
DB_USER = input("Please enter your database username: ")
DB_PASSWORD = input("Please input your database password: ")
DB_HOST = input("Please input the database URL: ")
DB_PORT = input("What port will you be connecting to for this session? ")
encoded_password = urllib.parse.quote_plus(DB_PASSWORD)
engine = sa.create_engine(f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
query = sa.text(f"select account_id, gross_profit, commissions FROM performance WHERE algorithm_id = {client_id};")
algo_performance = pd.read_sql_query(query,engine)
algo_performance = algo_performance[algo_performance['account_id'] == account]
algo_performance['net_profit'] = algo_performance['gross_profit']-algo_performance['commissions']
net_profit = algo_performance['net_profit'].sum()
if len(algo_performance) == 0:
    additional_contracts = 0
else:
    additional_contracts = int(np.floor(net_profit/2000))
print(f"Before we get started, let's detrmine our contract size: {1 + additional_contracts}\n")

#-------------------------------------------------------------------------------------------------------------------------------
                                        #Check if its trading time to start up the bot
#-------------------------------------------------------------------------------------------------------------------------------

# Run every min when close to trading hours skipping the first 2 mins that are super high volume and can bog down the algo
START_TIME = dt.time(7, 33)  # 7:33 AM MST
END_TIME = dt.time(14, 0)   # 2:00 PM MST

#Let's have it only run every 15 mins when well outside of trading hours
START_TIME2 = dt.time(7,15)
END_TIME2 = dt.time(14,15)

#Run a test to see if we should start running our bot, if not delay by a certain amount of time and try again.
try:
    while not rr.is_within_trading_hours(START_TIME2, END_TIME2):
        print(f"Well outside of Trading hours, will run every 15 mins... Current time: {dt.datetime.now().time()}")
        time.sleep(60*15)
    
    # Main loop to enforce trading hours
    while not rr.is_within_trading_hours(START_TIME, END_TIME):
        print(f"Outside trading hours. Waiting to start... Current time: {dt.datetime.now().time()}")
        time.sleep(60)  # Check every minute

except KeyboardInterrupt:
    print("Real-time update stopped by user.")


#-------------------------------------------------------------------------------------------------------------------------------
                                            #CONNECT TO IBKR (TWS or Gateway) BOT ID = 0
#-------------------------------------------------------------------------------------------------------------------------------

#Initialize our first instantiation of our TradingApp Class
app = rr.TradingApp()

##Create our socket
try:
    if live_or_sim.lower() == 'sim':
        #Simulated Accounts
        if TWS_or_gateway.lower() == 'tws':
            app.connect('127.0.0.1', 7497, clientId = 1) #TWS
        elif TWS_or_gateway.lower() == 'gateway':
            app.connect('127.0.0.1', 4002, clientId = 1) #Gateway; client Id can be up to 32 different clientId's
    elif live_or_sim.lower() == 'live':
        #Live Trading Accounts
        if TWS_or_gateway.lower() == 'tws':
            app.connect('127.0.0.1', 7496, clientId = 1) #TWS
        elif TWS_or_gateway.lower() == 'gateway':
            app.connect('127.0.0.1', 4001, clientId = 1) #Gateway

    time.sleep(2)

except:
    print('Failing to conenct to IBKR...')

##Create an event to start and stop our connection
stop_event = threading.Event()

#create and start our thread
connection_thread = threading.Thread(target=rr.websocket_connection,args=(app,stop_event))
connection_thread.start()
time.sleep(3)


#-------------------------------------------------------------------------------------------------------------------------------
                                            #Create Our Trading Strategy Function
#-------------------------------------------------------------------------------------------------------------------------------

#We put our strategy in a function that will run every 15 seconds (for this strategy) for the first 15 mins or so
def main():
    #---------------------------------------------------------------------------------------------------------------------------
                                                #Dynamic Variables
    #---------------------------------------------------------------------------------------------------------------------------

    #Let's Quickly Define the contract Symbols I will be using
    tickers = ['MNQ']
    symbol = 'MNQ'
    #Let's also define the contract expiration data for our futures contract to easily change
    expiration = '202503' #Needs to be updataed quarterly
    #How far back we will request historical data 
    time_period = '1 D'
    #Let's define our candle size as well
    candle_size = '5 mins'
    
    #---------------------------------------------------------------------------------------------------------------------------
                                     #Get our current postions and orders from IBKR
    #---------------------------------------------------------------------------------------------------------------------------

    #No filter for our execution dataframe
    filter = ExecutionFilter()

    #Let's call to IBKR to get a list of our current positions and orders
    app.reqPositions()
    app.reqOpenOrders()
    app.reqExecutions(1, filter)

    time.sleep(1) #This may need to be extended based on the amount of data

    #Let's get our position dataframes
    pos_df = pd.DataFrame(app.curr_position)
    pos_df.drop_duplicates(inplace=True, ignore_index=True)
    execution_df = pd.DataFrame(app.execution)
    
    if len(pos_df) != 0:
        print(f"\nPosition Dataframe: \n{pos_df.tail()}")
    else:
        print("\nNo positions have been opened yet today")
  
    #Let's get our Order Dataframes specific to the 'ClientId' to cancel or modify orders
    order_df = pd.DataFrame(app.order)
    order_df .drop_duplicates(inplace=True, ignore_index=True)
    
    if len(order_df) != 0:
        print(f"\nOrder Dataframe: \n{order_df.tail()}")
    else:
        print("\nCurrently no open orders for Algorithm")

    if len(execution_df) == 2:
        print(f"\nExecuted Trades: \n{execution_df}")
        execution_df['Details'] = execution_df['Details'].astype(str)
        small_exec = pd.DataFrame()
        small_exec['price'] = execution_df['Details'].str.extract(r"AvgPrice:\s*([0-9]*\.[0-9]*)").astype(float)
        small_exec['ClientId'] = execution_df['Details'].str.extract(r"ClientId:\s*([0-9]*)").astype(int)
        #Drop this execution table to only the Algorithm Executed trades
        small_exec = small_exec[small_exec['ClientId'] == client_id]
        #Pull out the values
        exit_price_trade_1 = small_exec['price'].iloc[-1]
        entry_price_trade_1 = small_exec['price'].iloc[0]
    elif len(execution_df) == 1:
        print(f"\nExecuted Trades: \n{execution_df}")
        execution_df['Details'] = execution_df['Details'].astype(str)
        small_exec = pd.DataFrame()
        small_exec['price'] = execution_df['Details'].str.extract(r"AvgPrice:\s*([0-9]*\.[0-9]*)").astype(float)
        small_exec['ClientId'] = execution_df['Details'].str.extract(r"ClientId:\s*([0-9]*)").astype(int)
        #Drop this execution table to only the Algorithm Executed trades
        small_exec = small_exec[small_exec['ClientId'] == client_id]
        #Pull out the values
        entry_price_trade_1 = small_exec['price'].iloc[0]
        print(f'\n Currently in an open position at ${entry_price_trade_1}')
    else:
        small_exec = pd.DataFrame()
        print("\nCurrently no trades have been executed")
    
    #---------------------------------------------------------------------------------------------------------------------------
                                    #Obtain our OHLCV Data from IBKR for trade execution
    #---------------------------------------------------------------------------------------------------------------------------

    #Let's request our historical data and create a dataframe. 
    for index,ticker in enumerate(tickers):
        print(f"\nBeginning passthrough for ticker: {ticker}")
        rr.histData(app, index,rr.usFut(ticker, expiration), time_period, candle_size)
        time.sleep(1) #This may be adjusted based on how much data we need to request
        getting_data = True
        t=1
        while getting_data:
            if len(app.data) != 0:
                print(f"Data Obtained in {t} second(s)")
                getting_data = False
            else:
                t += 2
                print(f"Not enough time to read data, giving more time")
                time.sleep(2)
        df = rr.dataToDataFrame(app,tickers) #Turn our data_dict into a dataframe
    
    #Because this is single ticker, let's pull the dataframe out of the dictionary
    df = df['MNQ']
    #Let's make sure the data is a datetime object
    df['Date'] = pd.to_datetime(df['Date'])

    if TWS_or_gateway.lower() == 'gateway':
        # Convert 'Timestamp' to datetime format and localize to UTC (IBKR default)
        df['Date'] = df['Date'].dt.tz_localize('UTC')  # Localize to UTC
        # Convert from UTC to MST
        df['Date'] = df['Date'].dt.tz_convert('America/Denver')  # Convert to MST
    
    #Set the index and pull the time out
    df = df.set_index('Date')
    df['Time'] = df.index.time

    #drop any NaN's and show the bottom of the dataframe for debugging
    df.dropna(inplace=True)
    print(df.tail())
    
    #----------------------------------------------------------------------------------------------------------------------------
                                       #Setup our Capital for the Trading Bot
    #----------------------------------------------------------------------------------------------------------------------------
    
    #We will dynamically adjust our contract sizes based on how the algorithm is performing. If it has made more than 
    #$2000 we will scale up an additional contract, and it will keep scaling for every $2000 we make. However, if we loose
    #money, it will dynamically decrease the amount we are risking as well.
    quantity = 1 + additional_contracts
    print(f"\nCurrent net profit of the algorithm is ${np.round(net_profit,2)}, so we are trading with {quantity} contract(s) today")
    
        
    if quantity == 0:
        print(f"Not enough capital to purchase MNQ futures contract")

    #------------------------------------------------------------------------------------------------------------------------------
                                #Let's Setup Our Initial Trade Criteria to start the day
    #------------------------------------------------------------------------------------------------------------------------------
    
    #Let's Setup our profit multiplier 
    profit_multiplier = 2
    high = None
    low = None
    
    #We just need to check the time conditions to get our trade data, we will save the order placement condtions for later.
    if df.iloc[-1]['Time'] == pd.to_datetime('07:35:00').time(): 
        high = df.iloc[-2]['High'] #Last row will be 7:35, so we need the high from 7:30 (-2 positions)
        low = df.iloc[-2]['Low'] #Last row will be 7:35, so we need the high from 7:30 (-2 positions)
        print(f"Time conditions met, looking for trade signals... \nHigh: ${high:.2f}, Low: ${low:.2f}")
    
    else:
        print("\nOutside of initial time conditions, no trades placed, let's check other conditions\n")
        
    #Once we have our Highs and Low's Let's calculate our profit targets
    if high != None:
        stop_size = high - low
        profit_target_long = high + (stop_size * profit_multiplier)
        profit_target_short = low - (stop_size * profit_multiplier)
        stop_loss_long = low
        stop_loss_short = high

    #--------------------------------------------------------------------------------------------------------------------------------
                                                #Setup our Trading Logic
    #--------------------------------------------------------------------------------------------------------------------------------

    #For now, we only want to take a single trade a day. If we have traded, our symbol will be in the position dataframe even 
    #if its closed. So, in this version, we will only place orders if the pos_df is empty and there are no open orders.
    
    #Get our order_id's ready
    app.reqIds(1)  # Request a new order ID
    
    while app.nextOrderId is None:
        print("Waiting for next valid order ID from IBKR...")
        time.sleep(1)
    
    order_id = app.nextOrderId 
    print(f"Using Order ID: {order_id}")

    
    #Make sure we haven't traded the symbol yet. The second argument hasn't been working. So we should check on this.
    if high != None:
        if (len(pos_df) != 0) or (len(order_df) != 0):
            print(f"\nThere are currently open orders or positions, so no new open orders will be placed")
            
        else:
            #I am going to call the specialized function to place a OCA order on both sides of the candle (see source code for details)
            rr.place_oca_bracket(app, order_id, quantity, high, profit_target_long, stop_loss_long, low,\
                                  profit_target_short, stop_loss_short, rr.usFut(symbol,expiration))
            print("\nOrder Placed")

    #------------------------------------------------------------------------------------------------------------------------------
                                #If we have been stopped out, let's see if we need to re-enter
    #------------------------------------------------------------------------------------------------------------------------------
    #We have to have already taken a position, no open orders, executed a second order to close our first position, 
    #and still have time for it to move to profit
    if (len(pos_df) != 0) and \
        (len(small_exec) == 2) and \
        (len(order_df) == 0) and \
        (df.iloc[-1]['Time'] < pd.to_datetime("13:30:00").time()): 
        
        #Get our order_id's ready just incase
        app.reqIds(-1)
        time.sleep(3)
        order_id = app.nextOrderId
        time.sleep(1)
        
        #Look for our conditions earlier
        entry_conditions_df = df[df['Time'] == pd.to_datetime('07:30:00').time()]
        high_trade_2 = entry_conditions_df.iloc[-1]['High']
        low_trade_2 = entry_conditions_df.iloc[-1]['Low']
        
        #Check to see what direction we went
        if entry_price_trade_1 > (high_trade_2 - 5):
            print(f"We went Long this morning")
            #Check to see if we stopped
            if exit_price_trade_1 < (low_trade_2 + 5): #Switched coparator
                print(f"We stopped, let's look to re-enter")
                profit_target = ((high_trade_2 - low_trade_2) * 2) + high_trade_2
                bracket_orders = rr.BracketOrder(order_id, 'BUY', quantity, high_trade_2, profit_target,\
                                                  low_trade_2, OrderType = 'STP LMT')
                for i, order in enumerate(bracket_orders):
                    app.placeOrder(order_id + i, rr.usFut(symbol,expiration), order)
                print("\nRe-entry Long Order Placed")
            else:
                print(f"Algorithm hit profit, congratulations!")
        elif entry_price_trade_1 < (low_trade_2 + 5):
            print(f"We went Short this morning")
            #Check to see if we stopped
            if exit_price_trade_1 > (high_trade_2 - 5):
                print(f"We stopped, let's look to re-enter")
                profit_target = low_trade_2 - ((high_trade_2 - low_trade_2) * 2)
                bracket_orders = rr.BracketOrder(order_id, 'SELL', quantity, low_trade_2, profit_target,\
                                                  high_trade_2, OrderType = 'STP LMT')
                for i, order in enumerate(bracket_orders):
                    app.placeOrder(order_id + i, rr.usFut(symbol,expiration), order)
                print("\nRe-entry Short Order Placed")
            else:
                print(f"Algorithm hit profit, congratulations!")
    else:
        print(f"No other conditions met, no trades placed")

    #---------------------------------------------------------------------------------------------------------------------------------
                                            #Cancel new position orders if not triggered by 1:30pm
    #---------------------------------------------------------------------------------------------------------------------------------
    if (df.iloc[-1]['Time'] >= pd.to_datetime("13:30:00").time()) and \
        (len(order_df) == 3) and \
        (pos_df[pos_df['Symbol'] == 'MNQ']['Position'][0] == 0.0):
        print(f"Position didn't trigger before our minimum time condition. Cancelling Orders...")
        order_to_cancel = order_df[order_df['Symbol'] == 'MNQ']['OrderId'][0]
        print(f"The order we need to cancel is {order_to_cancel}")
        app.cancelOrder(order_to_cancel)
        print(f"Order Cancelled")


#-------------------------------------------------------------------------------------------------------------------------------------
                                        #Set the conditions for the length our program will run
#-------------------------------------------------------------------------------------------------------------------------------------

#Set the duration we want to run our bot
starttime = time.time()
#How long we want to run the strategy (in seconds)
timeout = time.time() + (60 * 60 * 6.5) #run program for 6.5 hours
t = 0
while time.time() <= timeout:
    main() 
    app.clear_orders()
    app.clear_pos()
    app.clear_data()
    app.clear_execution()
    app.clear_acctsum()
    app.clear_pnl()
    t += 1
    print(f"\nAlgorithm completed round {t}, will run again in 3 seconds")
    time.sleep((3 * 1) - ((time.time() - starttime) % (3.0*1))) #update every 3s

#---------------------------------------------------------------------------------------------------------------------------------------
                                        #CLOSE PROGRAM AND DISCONNECT
#---------------------------------------------------------------------------------------------------------------------------------------

print(f"Algorithm has completed it's run through. Taking algorithm offline...")
##Turn off our connection
stop_event.set()
time.sleep(1)
app.disconnect()

time.sleep(1)
connection_thread.join()
print(f'Connection open? {app.isConnected()}...')