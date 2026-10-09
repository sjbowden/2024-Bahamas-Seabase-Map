"""The stories the chart tells: what happened, where, in the crew's own words.

Each is a passage from the journal one of the leaders kept that week, trimmed to
fit a bubble and otherwise left as he wrote it — first person, first names. The
journal itself is not in this repository; what is here is what was chosen to be
public.

Where a story sits. Ashore, it is where the thing happened rather than where the
boat lay: the lighthouse, the beach, the settlement. Afloat, it is the boat. Under
way, it is where the handheld's track puts the boat at the time given, so the
4.6 ft sounding sits abeam Tahiti Beach because that is where the log shows her
slowing to four knots at half past three.

`time` is local (EDT), and None where the journal gives a day but not an hour.
Keep the list in trip order — the export numbers the markers from it, and the
tests refuse a list that is not.
"""

STORIES = [
    # ------------------------------------------------------------ Sat 23 Mar
    dict(day="Sat 23 Mar", time="14:00", lon=-77.05192, lat=26.54688,
         title="Boarding the Adonai",
         text="After lunch the Seabase organizer met us and gave us an orientation. "
              "Then we met our captain, Josh, and boarded the Adonai, a 56-foot "
              "catamaran. Her mast is 78 feet tall. The captain showed us where to put "
              "our bags. The places were technically bedrooms, but certainly not big "
              "enough for all the people assigned to them to fit to sleep."),
    dict(day="Sat 23 Mar", time="14:48", lon=-77.08331, lat=26.55492,
         title="Out ahead of the storm",
         text="It was rainy and we hurried out of port to beat a storm blowing in. We "
              "were supposed to do a swim check right away, but as soon as we dropped "
              "anchor we heard thunder, so we waited for the storm to pass. Then we "
              "circled the boat, swam between the hulls and swam down to touch the "
              "anchor, about 10 feet deep. Because there was rain during the night, "
              "everyone found a place inside. It was pretty crowded."),

    # ------------------------------------------------------------ Sun 24 Mar
    dict(day="Sun 24 Mar", time="10:15", lon=-76.98717, lat=26.60034,
         title="The outer reef",
         text="We sailed to the outer reef, got together with buddies and put on fins "
              "and snorkel gear. The water wasn't calm, but it wasn't really rough. It "
              "was clear and we could see lots of fish: sergeant major fish, blue tang, "
              "a grouper, and a parrotfish. A few people found cool shells. All the "
              "fish were around clusters of coral."),
    dict(day="Sun 24 Mar", time="13:30", lon=-76.98495, lat=26.50092,
         title="The swings at Tahiti Beach",
         text="We swam from the boat to the beach. It was almost just a sandbar, but "
              "it connects to the main beach. Some of the boys played frisbee and "
              "football. There are two swings there, just in very shallow water, so we "
              "took pictures of us swinging. It was sunny, the water was clear and it "
              "wasn't very crowded. The beach was at low tide. At high tide it is "
              "covered by water."),
    dict(day="Sun 24 Mar", time="14:46", lon=-77.00992, lat=26.48635,
         title="The barge wreck",
         text="The wreck is some sort of a barge, only about 10 feet deep. The ship "
              "was covered in coral and there were fish everywhere. We snorkeled all "
              "around the ship. The water was very clear, and felt cool, but not cold."),
    dict(day="Sun 24 Mar", time=None, lon=-76.99067, lat=26.44881,
         title="Washing up in sea water",
         text="We washed dishes by scrubbing them with a soap-filled scrubber sponge. "
              "We sat on the back steps of the boat and used sea water. Then we would "
              "rinse, also with sea water. Finally, we would barely spritz them with "
              "fresh water from the fresh water tank, and laid them out to dry on the "
              "outside covered table."),

    # ------------------------------------------------------------ Mon 25 Mar
    dict(day="Mon 25 Mar", time="10:30", lon=-76.96220, lat=26.53970,
         title="Hope Town lighthouse",
         text="We anchored the Adonai and took the dinghy in, 10 people at a time. We "
              "first visited the lighthouse. It is the oldest operating "
              "kerosene-powered lighthouse. We climbed up the narrow spiral stairs; "
              "there were beautiful views from the top. The sun was out and the water "
              "was clear."),
    dict(day="Mon 25 Mar", time="14:00", lon=-76.95720, lat=26.53780,
         title="Vernon's famous pies",
         text="We stopped at Vernon's Grocery and looked around. Vernon told us the "
              "famous pies wouldn't be available until 2–3 pm. At 2 pm the grocery "
              "opened after their lunch break. We asked about pie and found out they "
              "wouldn't be ready for at least an hour, so we gave up on that."),
    dict(day="Mon 25 Mar", time="15:30", lon=-76.98750, lat=26.50250,
         title="4.6 feet under a 4.5 foot boat",
         text="We sailed through the area where we had gone to the beach with the "
              "swing. We didn't stop, but we went slow because it was a super low "
              "tide. The draft of the Adonai is 4.5 feet. At one point the depth meter "
              "was reading 4.6 feet. We sped up afterwards by letting out more sail."),
    dict(day="Mon 25 Mar", time="16:00", lon=-77.00720, lat=26.45833,
         title="“Dad…”",
         text="One funny thing that happened was Kyle asking me questions by saying, "
              "“Dad…” The captain said that every time Kyle says “Dad…” he had to do "
              "10 pushups. Within a few minutes Kyle had to do two sets."),
    dict(day="Mon 25 Mar", time="17:30", lon=-76.98400, lat=26.35683,
         title="A fire on the beach",
         text="We unloaded two kayaks and two paddleboards and used the kayaks to "
              "ferry people and dinner supplies to the beach. We built a fire from "
              "wood we scavenged and cooked hot dogs and chili over it. A path led to "
              "the other side of the island, where the waves are much rougher and the "
              "shore much rockier. Several older couples were cooking over their own "
              "fire. One of the men came over to talk. His grandson is a Boy Scout, so "
              "he filmed a short video of us saying hello."),
    dict(day="Mon 25 Mar", time="19:15", lon=-76.98492, lat=26.35683,
         title="Joy baths",
         text="Then we took Joy baths. Basically, lather up with Joy dish liquid and "
              "then jump into the water to rinse off."),
    # The launch is the one story with a fact added from outside the journal, which
    # took the two bright objects for two boosters. It was a Falcon 9 with a single
    # booster, scheduled for 7:42 pm EDT from Cape Canaveral, so the time is that.
    dict(day="Mon 25 Mar", time="19:42", lon=-76.98492, lat=26.35683,
         title="A rocket over the water",
         text="As we reboarded the ship we saw a plume in the sky. At first we thought "
              "it was a jet contrail, but it kept going. We then saw two bright "
              "objects separate from it. We were watching a SpaceX launch! It was a "
              "Falcon 9 carrying 23 Starlink satellites, launched from Cape Canaveral "
              "that evening. One of the bright objects was its booster, and we saw it "
              "fire its engines for a powered landing, on a drone ship out in the "
              "Atlantic. We also saw an amazing moonrise."),

    # ------------------------------------------------------------ Tue 26 Mar
    dict(day="Tue 26 Mar", time="10:30", lon=-77.00025, lat=26.32422,
         title="Little Harbour",
         text="We swam to the beach. Some people spent time harvesting, opening, and "
              "eating coconut. The rest hiked to an old and ruined lighthouse, where "
              "we could see the other side of the island, exposed to the open sea, "
              "with some intense waves. The settlement was a small community wrapped "
              "around a crystal clear and aquamarine bay with very white sand. "
              "Meanwhile Josh and Thomas went spearfishing. The tip of Thomas's spear "
              "got stuck in a hole and he had to cut it off, but he did bring back a "
              "spiny lobster antenna for us all to see and touch."),
    dict(day="Tue 26 Mar", time="14:15", lon=-76.98824, lat=26.39997,
         title="Cousteau's inside-out reef",
         text="Captain Josh told us that this reef is a favorite spot of Jacques "
              "Cousteau. He called it an inside-out reef because it is inside the "
              "breakwater reefs. It is also inside a protected park. We saw lots of "
              "sergeant major, stoplight parrotfish, blue tang and blue chromis, and "
              "also a needlefish, a turtle, and a large Caribbean reef shark. James "
              "dropped his Kindle over the side of the boat. Fortunately we were "
              "anchored in shallow water and someone dove down to get it."),
    dict(day="Tue 26 Mar", time="17:00", lon=-76.98220, lat=26.42340,
         title="Pelican Cay",
         text="Josh told us there were some ruins on the hill on the cay, but we never "
              "found the path to the top. We played on the sharp coral, watching the "
              "large waves hit the ocean side. They would strike the cay and send "
              "water 10 feet in the air, then the water would fall on us like rain. "
              "Nolan got hit by a particularly large wave. He was wearing Crocs; they "
              "broke, he got knocked down and sliced up his feet. Several people "
              "helped him to the beach, and Taylor brought a kayak to take him to the "
              "boat. Taylor was our appointed medic and he patched Nolan up."),
    dict(day="Tue 26 Mar", time="19:22", lon=-76.96814, lat=26.54166,
         title="As the lighthouse lit up",
         text="It was a beautiful afternoon and evening to sail, and a wonderful "
              "temperature. Harrison caught a mackerel on a line off the back of the "
              "boat. We anchored near Hope Town just as the lighthouse lit up. The "
              "cooking crew made pork chops, with applesauce, mashed potatoes, green "
              "beans and packets of mini Oreos for dessert."),

    # ------------------------------------------------------------ Wed 27 Mar
    dict(day="Wed 27 Mar", time="11:30", lon=-77.11280, lat=26.66800,
         title="Nippers, and a birthday",
         text="After dinghying to the dock we walked to Nippers and took the stairs "
              "down the dunes to the beach. It is a beautiful beach with big waves, "
              "because it is on the ocean side. The water was so clear and blue. It "
              "was Kyle's birthday. At the grocery store I told him he should get "
              "candy and I would pay for it. The cashier overheard and gave him a "
              "vanilla ice cream Drumstick."),
    dict(day="Wed 27 Mar", time="15:00", lon=-77.12776, lat=26.63458,
         title="Fishing for Megalodon",
         text="Josh trailed a rope behind the boat. Then people would climb into the "
              "water and hang onto the rope while wearing snorkel gear. Josh varied "
              "the speed between 2 and 6 knots. It was very cool to see the bottom fly "
              "by. Then you have to pull yourself along the rope against the current "
              "to get back to the boat. Lance fell off the rope once and we had to "
              "circle to get him. Dave's fingers cramped and he fell off too, so we "
              "had to circle around again."),
    dict(day="Wed 27 Mar", time="16:45", lon=-77.09693, lat=26.56951,
         title="The second barge",
         text="This wreck was shallower and there were tons of fish and wildlife: sea "
              "turtle, southern stingray, barracuda, pufferfish, Atlantic spadefish, "
              "lionfish, and many more."),
    dict(day="Wed 27 Mar", time="19:00", lon=-77.05373, lat=26.54891,
         title="The Captains Club",
         text="Dinner was chicken breasts, conch, the mackerel that Harrison caught "
              "and yellow jack with rice and salad. Then they brought out cake for "
              "Kyle. Josh led a rose–bud–thorn activity and shared his thoughts about "
              "the week. He said we are among the best groups he has captained for. He "
              "gave us our Seabase patches and added us to the Captains Club, which "
              "he doesn't always give out."),
]
