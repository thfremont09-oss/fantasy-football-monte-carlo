"""Words for search engines: each page's Google title and description, plus the guide articles.

Everything here is plain data. seo/site.py turns it into HTML; main.py reads the titles for the browser tab.
Titles stay under about 60 characters and descriptions under about 160, so Google shows them whole.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SITE = "https://montesportslab.com"
NAME = "Monte Sports Lab"
TAGLINE = "Best bets, live odds & fantasy lineups"


@dataclass
class Page:
    """One page of the app, as search engines see it before the app loads."""
    path: str                    # "" for home
    title: str
    description: str
    h1: str
    intro: str
    points: list[str] = field(default_factory=list)
    guides: list[str] = field(default_factory=list)      # related guide slugs
    nav: str = ""                                         # short name in the site menu


PAGES: list[Page] = [
    Page("", "Best Bets, Live Odds & Fantasy Lineups | Monte Sports Lab",
         "Today's best bets and live odds from DraftKings and Kalshi, plus the best fantasy lineup for NFL, FPL "
         "and F1 Fantasy. Every game simulated 1,000,000 times.",
         "Best bets, live odds and fantasy lineups",
         "Monte Sports Lab runs every game a million times and shows you where the numbers point: live scores with "
         "DraftKings and Kalshi odds side by side, today's best bets where our simulations disagree with the price, "
         "and the best fantasy lineup for your NFL, Fantasy Premier League and F1 Fantasy teams.",
         ["Live odds for the NFL, NBA, NHL, MLB, college sports and Europe's top soccer leagues",
          "Best bets today: our win chance next to the Kalshi price, with the exact payout for your stake",
          "Fantasy lineups for ESPN fantasy football, FPL and F1 Fantasy",
          "A public track record of how every pick did"],
         ["best-bets-today", "how-to-read-moneyline-odds", "best-fantasy-football-lineup"], "Home"),
    Page("live", "Live Odds & Scores: DraftKings vs Kalshi | Monte Sports Lab",
         "Live scores and odds for NFL, NBA, NHL, MLB, college and soccer: DraftKings moneylines, Kalshi prices and our simulated win chances, updated every 15 seconds.",
         "Live odds and scores",
         "Every game on today's board with the score, the DraftKings moneyline, spread and total, the Kalshi price "
         "and our own Monte Carlo win chance, refreshed every 15 seconds. Hover any line to see what it means in "
         "dollars, or open a game for stats and a chart of how the odds moved.",
         ["NFL, NBA, WNBA, NHL, MLB, college football and basketball",
          "Premier League, Champions League, La Liga, Bundesliga, Serie A, Ligue 1, MLS and more",
          "Search any team for its latest score and next game",
          "Schedules up to a week ahead for every league"],
         ["how-to-read-moneyline-odds", "kalshi-vs-draftkings", "point-spread-and-over-under-explained"], "Live odds"),
    Page("bets", "Best Bets Today: Our Picks vs Kalshi | Monte Sports Lab",
         "Today's best bets: teams our 1,000,000-game simulations rate higher than the Kalshi price, biggest gap "
         "first, with the exact payout for your stake.",
         "Best bets today",
         "Every game that hasn't started yet, simulated a million times and compared with what Kalshi charges. The "
         "teams where our chance is furthest above the price come first, with exactly what you'd get back for your "
         "stake after fees. Good value isn't the same as likely to win: many of these are underdogs.",
         ["Our simulated win chance next to the Kalshi price",
          "Exact payout for your stake, fees included",
          "DraftKings moneyline, spread and total for comparison",
          "Graded every day on the public track record"],
         ["best-bets-today", "implied-probability-and-expected-value", "kalshi-vs-draftkings"], "Best bets"),
    Page("players", "Player Stats: Season, Career & Last Game | Monte Sports Lab",
         "Search any NFL, NBA, WNBA, NHL, MLB, college or soccer player for stats this season, their career "
         "totals, their last game and live game, plus fun facts.",
         "Player stats",
         "Look up any player and see their numbers this season, over their whole career and in their last game, "
         "a live stat line while they're playing, and the most interesting things in their numbers: season "
         "highs, streaks, home and road splits and the milestones they're closing in on.",
         ["NFL, NBA, WNBA, NHL, MLB, college football and basketball, and soccer",
          "This season, career and last game side by side",
          "Live stats during a game", "Season highs, streaks and milestones"],
         ["best-fantasy-football-lineup", "best-fpl-team-this-gameweek"], "Player stats"),
    Page("football", "Best Fantasy Football Lineup This Week | Monte Sports Lab",
         "Who to start this week: connect your ESPN fantasy football league for your best lineup and your chance to beat this week's opponent, from 1,000,000 simulations.",
         "Best fantasy football lineup this week",
         "Connect your ESPN fantasy football league and we simulate your week a million times, using projections, "
         "recent games and injuries, to pick the lineup that gives you the best chance of beating this week's "
         "opponent. Tap any player to see why: who they're playing and who's guarding them.",
         ["Start/sit answers for every slot, including FLEX",
          "Your win chance against this week's opponent",
          "Built for ESPN leagues, public and private"],
         ["best-fantasy-football-lineup", "monte-carlo-simulation-sports"], "NFL fantasy"),
    Page("f1", "Best F1 Fantasy Team This Race | Monte Sports Lab",
         "The best F1 Fantasy team for this race: 5 drivers, 2 constructors and your DRS Boost pick under the $100M cap, from official prices and 1,000,000 simulations.",
         "Best F1 Fantasy team for this race",
         "We price every driver and constructor from the official F1 Fantasy game, simulate the race weekend a "
         "million times from recent form and results, and pick the 5 drivers and 2 constructors that score the most "
         "inside the cost cap, plus who should get the DRS Boost.",
         ["Official F1 Fantasy prices", "Best team under the $100M cost cap", "DRS Boost (2x) pick",
          "Results from every past round on the track record"],
         ["best-f1-fantasy-team"], "F1 Fantasy"),
    Page("fpl", "Best FPL Team This Gameweek | Monte Sports Lab",
         "Fantasy Premier League: the best XI, bench and captain for this gameweek on any budget, from xG, xA, "
         "minutes and fixtures, simulated 1,000,000 times.",
         "Best FPL team this gameweek",
         "Pick the best Fantasy Premier League squad for this gameweek on any budget. Every player's points are "
         "simulated from expected goals and assists, minutes and the fixture, and we pick the XI, bench and captain "
         "that score the most while following every FPL rule.",
         ["Best XI, bench order and captain", "Any budget, max 3 players per club", "Built on xG, xA, minutes and fixtures"],
         ["best-fpl-team-this-gameweek"], "FPL"),
    Page("parlays", "Best Parlay Picks Today | Monte Sports Lab",
         "Find the best parlays for your risk and payout from 80,000+ DraftKings and Kalshi markets, each tested on "
         "1,000,000 simulated slates.",
         "Best parlay picks today",
         "Tell us how much risk you want and what payout you're after, and we search tens of thousands of DraftKings "
         "and Kalshi markets for the parlays with the best chance of hitting, each one checked against a million "
         "simulated slates.",
         ["Choose your risk and target payout", "DraftKings and Kalshi markets", "True hit chance for every parlay"],
         ["how-parlays-work"], "Parlays"),
    Page("niche", "Niche Sports Betting Picks | Monte Sports Lab",
         "The most unusual markets on the board, from table tennis to darts and esports, with simulated chances "
         "and payouts.",
         "Niche sports picks",
         "Off the beaten path: the most obscure markets on the board, from darts and table tennis to lower-league "
         "soccer, run through the same million-slate simulation as our parlays.",
         ["Obscure leagues and sports", "Simulated hit chance for every pick"],
         ["how-parlays-work"], "Niche sports"),
    Page("march-madness", "March Madness Bracket Predictions | Monte Sports Lab",
         "March Madness bracket predictions: title odds for every team and a full bracket to fill out, from every Division I result, simulated 1,000,000 times.",
         "March Madness bracket predictions",
         "Every Division I score this season feeds team ratings, and the whole tournament is played out a million "
         "times. You get each team's chance of reaching every round and a complete bracket to fill out.",
         ["Title and Final Four odds for every team", "A full bracket pick", "Upset picks worth making"],
         ["march-madness-bracket-predictions"], "March Madness"),
    Page("track-record", "Track Record: How Our Picks Did | Monte Sports Lab",
         "How every Monte Sports Lab pick has done on real results: best bets, F1 Fantasy teams, FPL squads and "
         "NFL lineups, graded against what actually happened.",
         "Our track record",
         "We grade our picks against real results: Fantasy Premier League squads, NFL lineups and F1 Fantasy teams "
         "against the points they actually scored, and our best bets against the final scores, with a running "
         "profit chart.",
         ["FPL, NFL and F1 Fantasy results", "Best bets graded daily, with running profit"],
         ["monte-carlo-simulation-sports"], "Track record"),
    Page("how-it-works", "How It Works: 1,000,000 Simulations | Monte Sports Lab",
         "How Monte Sports Lab picks bets and fantasy lineups: Monte Carlo simulation of every game a million "
         "times, explained in plain English.",
         "How it works",
         "Every number on the site comes from Monte Carlo simulation: we play each game, race or gameweek a million "
         "times with realistic randomness and count how often each result happens. Here is what goes into each "
         "model, in plain English.",
         ["Where the data comes from", "How each sport is simulated", "Why a million runs"],
         ["monte-carlo-simulation-sports", "implied-probability-and-expected-value"], "How it works"),
]
PAGE_BY_PATH = {p.path: p for p in PAGES}


@dataclass
class Guide:
    """A plain article that answers one search, then points to the tool that does it for you."""
    slug: str
    title: str
    description: str
    h1: str
    lede: str
    sections: list[tuple[str, list[str]]]
    faq: list[tuple[str, str]]
    cta: tuple[str, str]           # (app path, button text)
    nav: str


GUIDES: list[Guide] = [
    Guide(
        "best-bets-today", "Best Bets Today: How We Find Them | Monte Sports Lab",
        "Today's best sports bets, found by simulating every game 1,000,000 times and comparing our win chance with the Kalshi price. How it works and how to use it.",
        "Best bets today, and how we find them",
        "A good bet isn't a team you think will win. It's a price that's too low for the team's real chance. Our "
        "Best Bets page finds those prices every day by simulating each game a million times and comparing the "
        "result with what Kalshi is charging.",
        [("What makes a bet \"best\"",
          ["Every price implies a chance. If a Kalshi contract on the Knicks costs 40¢, the market is saying the "
           "Knicks win about 40% of the time. If our simulations say 48%, that's an 8-point gap in your favour: over "
           "many bets like it, you'd expect to come out ahead.",
           "So we rank today's games by that gap, biggest first. A big gap doesn't mean a sure thing. Plenty of "
           "our best bets are underdogs that will lose more often than they win. They're on the list because the "
           "payout is bigger than their risk."]),
         ("How the simulation works",
          ["For every game that hasn't started, we build each team's strength from its record and home advantage, "
           "then play the game a million times. Football and basketball use a scoring-margin model; hockey, soccer "
           "and baseball use goal and run counts. The share of simulated wins is our chance.",
           "We skip teams with fewer than 8 games played, because early-season records say too little, and prices "
           "near 0% or 100%, where small differences don't mean much."]),
         ("How to use the list",
          ["Enter your stake and every pick shows exactly what you'd get back, Kalshi's fee included. Compare it "
           "with the DraftKings moneyline on the same card; hover any line for what it means in dollars.",
           "Spread small stakes across several picks rather than one big bet, and check our public track record to "
           "see how the picks have done."])],
        [("Are best bets guaranteed to win?",
          "No. A best bet is one where we think the price is too low for the real chance. Many are underdogs that "
          "lose more often than they win; the value comes from the bigger payout over many bets."),
         ("Where do the odds come from?",
          "Prices come from Kalshi and DraftKings (via ESPN). Our own chances come from simulating each game "
          "1,000,000 times."),
         ("How often is the list updated?",
          "Every time you open the page. Prices move all day, so the list can change by the minute.")],
        ("bets", "See today's best bets"), "Best bets today"),
    Guide(
        "how-to-read-moneyline-odds", "Moneyline Odds Explained: What +150 and -200 Mean | Monte Sports Lab",
        "What do +150 and -200 mean in betting? Moneyline odds explained simply: what you win, the chance behind every line, and how they compare with Kalshi.",
        "Moneyline odds explained: what +150 and -200 mean",
        "A moneyline is a bet on who wins, written as a number with a plus or a minus. The sign tells you who's "
        "the favourite, and the number tells you the payout. Here's how to read one in ten seconds.",
        [("Plus numbers: the underdog",
          ["+150 means a $100 bet wins $150 profit, and you get your $100 back too, so $250 in total. Bet $10 and "
           "you'd win $15.",
           "The bigger the plus number, the bigger the underdog and the bigger the payout."]),
         ("Minus numbers: the favourite",
          ["-200 means you must bet $200 to win $100 profit. Bet $10 and you'd win $5.",
           "The bigger the minus number, the bigger the favourite and the smaller the payout."]),
         ("Turning a moneyline into a chance",
          ["Every moneyline hides a win chance. For a plus line: 100 ÷ (line + 100). So +150 is 100 ÷ 250 = 40%. "
           "For a minus line: line ÷ (line + 100), ignoring the minus. So -200 is 200 ÷ 300 = 67%.",
           "Add both teams' chances and you'll get a bit more than 100%. The extra few points are the sportsbook's "
           "cut (the vig). Remove it and you get the book's fair estimate of each team's chance."]),
         ("Moneylines vs Kalshi prices",
          ["Kalshi skips the plus and minus: a contract costs between 1¢ and 99¢ and pays $1 if you're right. A "
           "40¢ price is a 40% chance, roughly the same as a +150 moneyline. Our Live Odds page shows both side by "
           "side, and you can hover any line for its meaning in dollars."])],
        [("What does +100 mean?", "Even money: a $100 bet wins $100 profit. It implies a 50% chance."),
         ("Is -110 good?",
          "-110 is the standard price on spreads and totals: bet $110 to win $100. It implies about 52.4%, so you "
          "need to win more than that often to profit."),
         ("Do I get my stake back?",
          "Yes. The moneyline shows profit only; a winning bet also returns your stake.")],
        ("live", "See live moneylines"), "Moneyline odds"),
    Guide(
        "kalshi-vs-draftkings", "Kalshi vs DraftKings Odds: Which Pays More? | Monte Sports Lab",
        "Kalshi vs DraftKings: how exchange prices compare with sportsbook moneylines, how to convert between them, and how to find the better payout.",
        "Kalshi vs DraftKings: comparing the odds",
        "Kalshi and DraftKings both let you back a team to win, but they price it differently. DraftKings is a "
        "sportsbook that sets moneylines; Kalshi is an exchange where traders buy and sell contracts that pay $1. "
        "The same team can pay noticeably more on one than the other.",
        [("How each one prices a game",
          ["DraftKings writes odds like -150 or +130, with its margin built in. Kalshi shows a price like 58¢: you "
           "pay 58¢ and get $1 back if your team wins, minus a small trading fee.",
           "To compare them, turn both into chances. A 58¢ Kalshi price is 58%; a -150 moneyline is 150 ÷ 250 = "
           "60%. Lower implied chance for the same team means a better payout for you."]),
         ("When Kalshi pays more, and when DraftKings does",
          ["Kalshi's fee is largest for prices near 50¢ and small near the extremes, while a sportsbook's margin is "
           "spread across both sides. Underdogs and lopsided games often price differently on the two, so it pays "
           "to check both every time.",
           "Our Live Odds page lines them up on every card: score, DraftKings moneyline, Kalshi price and our own "
           "simulated chance."]),
         ("Where our numbers fit in",
          ["A third opinion helps. We simulate each game a million times from team records and home advantage. "
           "When our chance is well above both prices, the game shows up on Best Bets."])],
        [("Is Kalshi legal for sports?",
          "Kalshi is a US exchange regulated by the CFTC. Availability of sports contracts can depend on your "
          "state, so check Kalshi's own rules for where you live."),
         ("How do I convert a Kalshi price to a moneyline?",
          "Under 50¢: +(100 - price) ÷ price × 100, so 40¢ is +150 and 25¢ is +300. Over 50¢: -price ÷ "
          "(100 - price) × 100, so 60¢ is -150 and 75¢ is -300. Our site shows the conversion on every card.")],
        ("live", "Compare Kalshi and DraftKings live"), "Kalshi vs DraftKings"),
    Guide(
        "point-spread-and-over-under-explained", "Point Spread & Over/Under Explained Simply | Monte Sports Lab",
        "What does -3.5 mean in betting? Point spreads and over/under totals explained with simple examples, plus "
        "how -110 pricing works.",
        "Point spreads and over/unders, explained simply",
        "Besides picking the winner, the two most common bets are the spread (by how much) and the total (how many "
        "points in all). Both come with a price, usually around -110.",
        [("The point spread",
          ["A spread evens out a mismatch. If the Chiefs are -3.5, they must win by 4 or more for a Chiefs bet to "
           "win. Their opponent at +3.5 wins the bet if they win outright or lose by 3 or fewer.",
           "Half points (the .5) mean there can't be a tie, called a push. With a whole number like -3, a 3-point "
           "win is a push and you get your stake back."]),
         ("The over/under (total)",
          ["The total is the combined score of both teams. If it's 47.5, an over bet wins if the teams score 48 or "
           "more together; an under bet wins on 47 or fewer. It doesn't matter who wins."]),
         ("The -110 price",
          ["Spreads and totals usually cost -110: bet $110 to win $100, or $10 to win about $9.09. That means you "
           "need to win about 52.4% of the time to break even. On our Live Odds page, hover any spread or total to "
           "see it in dollars for a $10 bet."])],
        [("What does +7 mean?", "The team can lose by up to 6 and the bet still wins; losing by exactly 7 is a push."),
         ("Is the spread or the moneyline better?",
          "Neither is always better. The moneyline only needs a win; the spread pays similar odds on both sides "
          "but needs the margin.")],
        ("live", "See today's spreads and totals"), "Spreads & totals"),
    Guide(
        "implied-probability-and-expected-value", "Implied Probability & Expected Value in Betting | Monte Sports Lab",
        "How to turn any betting odds into a win chance, what expected value means, and how to tell a good-value "
        "bet from a likely winner. Simple formulas and examples.",
        "Implied probability and expected value, simply",
        "Two ideas separate smart bets from hunches: the chance a price implies, and whether your own estimate of "
        "the chance is higher. That difference, over many bets, is your expected value.",
        [("Implied probability",
          ["Every price is a chance in disguise. Kalshi: the price in cents is the chance (35¢ = 35%). Moneyline: "
           "+150 is 100 ÷ 250 = 40%, and -150 is 150 ÷ 250 = 60%. Decimal odds: 1 ÷ odds, so 2.50 is 40%."]),
         ("Expected value",
          ["Expected value is what a bet is worth on average. Suppose a Kalshi contract costs 40¢ and you believe "
           "the true chance is 50%. Half the time you win 60¢, half the time you lose 40¢: on average +10¢ per "
           "contract, before fees.",
           "Positive expected value doesn't mean this bet will win. It means that bets like it should come out "
           "ahead over time, if your chances are right."]),
         ("Value isn't the same as likely",
          ["A 30% underdog priced at 20¢ is a better bet than an 80% favourite priced at 85¢, even though the "
           "favourite usually wins. That's why our Best Bets list is full of underdogs, and why we grade it on "
           "profit, not just wins."])],
        [("What is a +EV bet?",
          "A bet whose payout is bigger than its risk, judged by your estimate of the true chance."),
         ("How do I estimate the true chance?",
          "That's the hard part. We do it by simulating each game a million times; you can compare our number "
          "with the market on every game.")],
        ("bets", "See today's best-value bets"), "Expected value"),
    Guide(
        "how-parlays-work", "How Parlays Work & How to Pick Better Ones | Monte Sports Lab",
        "How parlays pay out, why they're hard to hit, and how to pick better ones, with payout math for -110 legs and a tool that tests parlays 1,000,000 times.",
        "How parlays work, and how to pick better ones",
        "A parlay joins several bets into one. Every leg has to win, and in return the payouts multiply. That's "
        "what makes them exciting, and what makes them lose so often.",
        [("How the payout multiplies",
          ["Turn each leg into decimal odds and multiply. A -110 bet is 1.91 in decimal. Two of them: 1.91 × 1.91 = "
           "3.64, so a $10 two-leg parlay returns about $36.45 (+264). Three legs: about +596.",
           "Each extra leg also multiplies the risk. Two coin-flip legs hit 25% of the time; four hit about 6%."]),
         ("Why parlays are hard",
          ["The sportsbook's margin is on every leg, so it stacks up as you add legs. And legs aren't always "
           "independent: a team winning big often goes with the over, which books account for in same-game "
           "parlays."]),
         ("Picking better parlays",
          ["Use fewer legs, and only legs where the price looks generous. Our Parlay Lab searches tens of thousands "
           "of DraftKings and Kalshi markets for your chosen risk and payout, then checks every candidate against a "
           "million simulated slates to report its real chance of hitting."])],
        [("How many legs should a parlay have?",
          "Fewer is usually better: two or three legs keep the hit rate reasonable."),
         ("What happens if one leg pushes?",
          "At most sportsbooks the leg is removed and the parlay pays at the reduced odds; check your book's rules.")],
        ("parlays", "Build a parlay in Parlay Lab"), "Parlays"),
    Guide(
        "best-fantasy-football-lineup", "Best Fantasy Football Lineup This Week: Who to Start | Monte Sports Lab",
        "Who to start in fantasy football this week: set your best lineup with projections, matchups and injuries, and simulate your ESPN matchup 1,000,000 times.",
        "Best fantasy football lineup this week: who to start",
        "Setting your lineup comes down to one question each week: which players give you the best chance of "
        "beating this particular opponent? Here's how to think about it, and a tool that does the math for you.",
        [("Start with projections, then adjust",
          ["Projections are the baseline: expected points given the matchup. Adjust for what they miss: a backup "
           "promoted by an injury, a quarterback out, bad weather, a team resting starters."]),
         ("Matchups matter, especially at WR",
          ["A receiver facing a top shutdown cornerback usually scores less than his average; a running back "
           "against a run defense that's allowing big games usually more. Our tool shows who each player faces "
           "and who's guarding them."]),
         ("Play for the win, not the most points",
          ["If you're a big underdog this week, you want upside: boom-or-bust players who can score 30. If you're "
           "a big favourite, take the steady floor. Simulating the whole week a million times captures this "
           "automatically: we pick the lineup with the highest chance of beating your opponent, not just the "
           "biggest projection."]),
         ("Use it on your ESPN league",
          ["Connect your ESPN league (public or private) and you'll get your best lineup, every start/sit call and "
           "your win chance for the week."])],
        [("Who should I start at FLEX?",
          "The player whose range of outcomes gives you the best chance of winning this matchup, which isn't "
          "always the highest projection. Our tool checks every FLEX option."),
         ("Does it work with Yahoo or Sleeper?", "The lineup tool connects to ESPN leagues today.")],
        ("football", "Get your best lineup"), "Fantasy football lineup"),
    Guide(
        "best-fpl-team-this-gameweek", "Best FPL Team This Gameweek: Picks & Captain | Monte Sports Lab",
        "How to pick the best FPL team this gameweek: budget, fixtures, xG and captain choice, plus a tool that picks your XI and captain for any budget.",
        "Best FPL team this gameweek: picks and captain",
        "Fantasy Premier League gives you £100m for 15 players, at most 3 from any club, and your captain scores "
        "double. The best team for a single gameweek is the one with the most expected points that follows all "
        "those rules.",
        [("The rules that shape every team",
          ["15 players: 2 goalkeepers, 5 defenders, 5 midfielders and 3 forwards, with no more than 3 from one "
           "club. Your starting XI needs 1 goalkeeper, at least 3 defenders, 2 midfielders and 1 forward."]),
         ("What actually predicts points",
          ["Expected goals (xG) and expected assists (xA) predict future goals better than past goals do. Minutes "
           "matter as much: a rotation risk on a big club often scores less than a nailed-on starter on a smaller "
           "one. Then the fixture: home games against weak defences lift attackers; clean-sheet chances lift "
           "defenders and keepers."]),
         ("Choosing your captain",
          ["Captain the player with the highest expected points, usually a premium attacker at home against a weak "
           "side. Because the captain doubles, even a small edge here matters more than anywhere else."]),
         ("Let the simulation do it",
          ["Our FPL tool simulates every player's gameweek a million times from xG, xA, minutes and fixtures, then "
           "picks the XI, bench order and captain with the most points for your budget."])],
        [("What's a good FPL budget split?",
          "Most strong teams spend heavily on two or three premium attackers and fill out defence with value "
          "picks; the right split depends on fixtures that week."),
         ("Who should I captain this gameweek?",
          "Open the FPL page: it names the captain with the highest expected points for this gameweek.")],
        ("fpl", "Pick my FPL team"), "FPL team"),
    Guide(
        "best-f1-fantasy-team", "Best F1 Fantasy Team: Drivers, Constructors & DRS | Monte Sports Lab",
        "How to pick the best F1 Fantasy team: 5 drivers and 2 constructors under the $100M cap, plus your DRS Boost, with every race simulated 1,000,000 times.",
        "Best F1 Fantasy team: drivers, constructors and DRS Boost",
        "The official F1 Fantasy game gives you a $100M cost cap for 5 drivers and 2 constructors, and one driver "
        "scores double with the DRS Boost. Points come from qualifying, the race, overtakes and more, so the best "
        "team is about value, not just the fastest car.",
        [("Value beats star power",
          ["The top drivers score the most but cost the most. A midfield driver who regularly outscores their price "
           "point often adds more per million than a front-runner, and frees budget for a top constructor."]),
         ("Constructors count twice",
          ["Constructor points combine both drivers, so a team with two consistent finishers often scores more "
           "reliably than one star and a struggling team-mate."]),
         ("Who gets the DRS Boost",
          ["Give the DRS Boost (2x) to the driver with the highest expected points, usually a front-runner who "
           "starts well and rarely retires. Our tool names the best DRS pick for every race."]),
         ("How we pick",
          ["We take official F1 Fantasy prices, simulate the race weekend a million times from recent form and "
           "results, and choose the team with the most expected points under the cap."])],
        [("How much is the F1 Fantasy budget?", "The cost cap starts at $100M; prices change through the season."),
         ("How many transfers do I get?",
          "Two free transfers per race in the official game; extra ones cost points.")],
        ("f1", "Pick my F1 Fantasy team"), "F1 Fantasy team"),
    Guide(
        "march-madness-bracket-predictions", "March Madness Bracket Predictions & Upset Picks | Monte Sports Lab",
        "March Madness bracket predictions from 1,000,000 simulated tournaments: title odds for every team, upsets worth picking and tips to win your pool.",
        "March Madness bracket predictions and upset picks",
        "With 63 games and countless upsets, nobody fills out a perfect bracket. But you can fill out a smart one. "
        "Simulating the tournament a million times shows each team's real chance of reaching every round.",
        [("How we predict the tournament",
          ["Every Division I result this season feeds team ratings that adjust for opponent strength and margin. "
           "Then we play the whole bracket a million times, game by game, and count how far each team gets."]),
         ("Picking upsets that are worth it",
          ["Seeds are a rough guide. A 12 seed with a strong rating against a weak 5 seed can be close to a coin "
           "flip, and those are the upsets worth picking. A 16 over a 1 almost never is."]),
         ("Winning your pool",
          ["In a big pool, picking the same favourite as everyone else won't separate you. A strong champion pick "
           "that fewer people choose can be worth more than the single most likely winner."])],
        [("When are the predictions available?",
          "As soon as the bracket is set on Selection Sunday, and the ratings run all season."),
         ("What's the most likely Final Four?",
          "Open the March Madness page for each team's chance of reaching the Final Four.")],
        ("march-madness", "See bracket predictions"), "March Madness"),
    Guide(
        "monte-carlo-simulation-sports", "Monte Carlo Simulation for Sports Betting, Explained | Monte Sports Lab",
        "What Monte Carlo simulation is and how it predicts sports: playing each game a million times to turn ratings into win chances and fantasy lineups.",
        "Monte Carlo simulation for sports, explained",
        "Monte Carlo simulation means answering a question about chance by playing it out many times with "
        "realistic randomness and counting what happens. It's how we turn team ratings into win chances.",
        [("The idea in one example",
          ["Say one team is expected to win by 3 points, and real results vary around the expectation by about 13 "
           "points. Play the game a million times, each with its own random swing, and count the wins: about 59%. "
           "That's the team's win chance."]),
         ("Why a million times",
          ["With a thousand runs, the answer can wobble by a few percentage points. With a million, it's steady "
           "to a tenth of a point, which matters when you're comparing it with a price."]),
         ("Different sports, different models",
          ["Football and basketball are about the margin, so we simulate the scoring margin. Hockey, soccer and "
           "baseball are about counts of goals and runs, so each team's total is drawn on its own. Fantasy "
           "lineups simulate every player's points; brackets simulate every round."]),
         ("Where it can go wrong",
          ["A simulation is only as good as its inputs. Records don't know about an injury announced an hour ago. "
           "That's why we publish a track record of how our picks actually did."])],
        [("Is Monte Carlo simulation accurate?",
          "It's exact about its own assumptions; how accurate it is about real games depends on those assumptions. "
          "Check our track record."),
         ("Why is it called Monte Carlo?", "After the famous casino in Monaco, because the method runs on chance.")],
        ("how-it-works", "Read how our models work"), "Monte Carlo"),
]
GUIDE_BY_SLUG = {g.slug: g for g in GUIDES}
