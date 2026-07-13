We will follow a test and improve , test case driven development approach .  ALl code will be in Pygame / Python. At each step you will complete an executable code that can be copied and pasted into a dev environment to be run and given feedback. We will continue iterating till I give go ahead when we can move to the next step  . At each step you can build context required for that step using the same Product document , This guideline and the latest iteration of approved code in your context window. Any context handled over and above that is upto you . 

Steps that we can follow in the below order 
1) Develop a simple UI . Layout , colour scheme, theme , font, spacing of board, and different sections with dummy info . 
2) Read the "Layout.xlsx" file which is a spread sheet. Sheet named "boardstate" has the piece placement defined by the cells in column A through H & Rows 2 to 27. Row 1 and 28 have the file names ( a, b , c, to h) and are just duplicates of each other. Column I has the ranks mentioned.   Within the table each piece is written where it has to be placed. The piece convention is same as chess where p is pawn, K is king, N is knight, B is bishop, R is rook. Black player pieces have prefix of 2 before the piece, white player pieces in upper case, neutral pieces are written with a prefix of N .  The outcome of this step is that this file can be read and replicated within the board in the UI created in the previous step.
3) In this step would like to ensure the clicking ans selecting of piece along with moving etc works . 
4) Would like to see if the moves made are getting recorded per logic and displayed correctly on the game screen
5) Would like to see if the points system works for increment with each move
6) Would like to see if the timers work with switching between the players turns . 
7) Check the promotion display , input and logic works
8) Would like the neutral pieces to move to any random move thats valid 
9) Would  like to ensure full game loop works after playing a game till the end & check for draw / win criterion
10) At end of full game in the chess png type format with all the moves made must be recorded and saved in a file asking the user for the name to be used. 
11) Check the pause / unpause and restart game buttons work 
12) Would like to add fog of war and see if only the active board is displayed as the player turn switches
13) Would like to add a chess bar displaying the evaluation of the active board passed to STock fish AI.  
14) now test active board that can be passed to the chess engine and the top 5 moves are printed onto the terminal for each player, the neutral player . 
15) Now we can integrate the AI for neutral pieces 
16) Now add a single player mode where the player can start a game against computer . 

Programming guidelines
- All code must be modular, Commented exhaustively for human understanding and have enough logging built in for in game debugging . 
- You can club 1 or 2 of the above steps in groups but at each check point we must have code that can be copy pasted into an IDE executed , tested by human and then approved for further development
- Use PyGame , Python to code 
- As the game mimics Chess to large extent you can learn from public Python based Chess source code to develop. 
- Ask any questions as needed through out the development . This is not a speed run but to build robust code that works in a test driven incremental methodology
- Make the code flexible where needed, we will be adding sprites , color theme options, Background music, In Game event driven sound and graphic effects at a later stage so plan for such a scalable architecture. 
- When overhauling the architecture or making any major choices which may affect scalability , ask for confirmation before you start coding.
