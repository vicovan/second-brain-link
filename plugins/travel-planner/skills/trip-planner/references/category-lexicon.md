# Category lexicon — how `taste.py` guesses what a place is

`taste.py` reads this file. Each bullet is `- <category> (<group>, <price band>): word, word, …`.
A place's name, its saved-list names, its `place/tag/*` tags and its review text are matched
against the words (case-insensitive, whole words; a phrase may contain spaces). The first
category with the most hits wins; no hit leaves it `other`.

The price band is a default for the category, not a fact about the place — `$` cheap, `$$`
mid, `$$$` expensive, `-` not applicable. It is a hint for `taste-scout`, and `taste.md` is a
file the user confirms and corrects, because heuristics over names will sometimes be wrong.

Edit freely. Add words, not new syntax.

## Food & drink

- coffee (drink, $): coffee, café, cafe, espresso, roastery, roasters, pour-over, pour over, third wave, third-wave, flat white, barista, brew bar
- tea (drink, $): tea, teahouse, matcha, chai, tea room
- bakery (food, $): bakery, pastry, patisserie, boulangerie, pastelaria, croissant, bagel, donut
- ramen (food, $): ramen, noodle, udon, soba, pho
- sushi (food, $$$): sushi, omakase, izakaya, sashimi
- tapas (food, $$): tapas, tasca, petiscos, pintxos, mezze, meze
- seafood (food, $$): seafood, fish, oyster, marisqueira, crab
- fine-dining (food, $$$): fine dining, tasting menu, michelin, degustation, chef's table
- market (food, $): market, mercado, food hall, hawker, street food, food court
- pizza (food, $): pizza, pizzeria, trattoria, pasta, osteria
- restaurant (food, $$): restaurant, bistro, brasserie, diner, kitchen, grill, eatery, canteen, dinner, lunch, brunch
- wine-bar (drink, $$): wine bar, vinho, enoteca, natural wine, wine
- cocktail-bar (drink, $$): cocktail, speakeasy, listening bar, jazz bar
- bar (drink, $$): bar, pub, tavern, brewery, taproom, beer, sake, izakaya
- hotel-breakfast (food, $$): hotel breakfast, buffet breakfast, breakfast hall

## Culture & sights

- museum (culture, $): museum, museu, gallery, exhibition, collection, art centre, art center
- music (culture, $$): fado, concert, live music, opera, jazz, club, venue
- viewpoint (sight, -): viewpoint, miradouro, lookout, observation deck, tower, skyline, rooftop
- landmark (sight, -): cathedral, church, temple, shrine, palace, castle, monastery, fortress, bridge, square, plaza
- garden (nature, -): garden, park, botanical, jardim, greenhouse
- beach (nature, -): beach, praia, bay, cove, seafront
- trail (nature, -): trail, hike, hiking, ridge, mountain, summit, walk, climb, bouldering

## Shopping & other

- bookshop (shop, $$): bookshop, bookstore, books, livraria
- design-shop (shop, $$): design, ceramics, tiles, azulejo, craft, concept store, vintage
- market-shop (shop, $): flea market, antiques, bazaar
- coworking (work, $$): coworking, co-working, workspace, office, hub
- event-venue (event, -): arena, expo, convention, conference, summit, hall
- transport (transport, -): airport, station, terminal, pier, port, ferry

## Review words

`taste.py` also reads these to nudge a place's love score. Keep each list short.

- love+ : best, loved, favourite, favorite, perfect, amazing, went back, go back, return, gem, must, wonderful, great
- love- : forgettable, avoid, overpriced, rude, dirty, disappointing, meh, never again, tourist trap, would rather
