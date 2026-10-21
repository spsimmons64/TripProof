###################################################################################################
# What license a vehicle calls for.
#
# It follows the vehicle and nothing else. The program a company runs under - Medicaid, a CTC, a
# Chapter 14-90 transit system - decides what else is asked of the driver, never which class of
# license they must hold to sit in that seat.
#
# Two lines matter, and both are counted the way the rules count them:
#   seats  designed to carry more than 15 people INCLUDING the driver -> a passenger commercial
#          vehicle, so a CDL with the passenger endorsement
#   gvwr   26,001 lb or more -> a commercial vehicle by weight; Class B for a single vehicle
#
# A vehicle under both lines needs no commercial license at all: in Florida that is an ordinary
# Class E. Nothing here guesses - a vehicle whose seats and weight are unknown says so.
###################################################################################################
PASSENGER_SEATS = 16          # more than 15 including the driver
HEAVY_GVWR = 26_001


def license_for(vehicle: dict) -> dict:
    """What a driver must hold to drive this one, as far as the record allows us to say."""
    seats, gvwr = vehicle.get("seats"), vehicle.get("gvwr")
    if not seats and not gvwr:
        return {"known": False, "cdl": None, "endorsement": None,
                "summary": "Not known - record the seating capacity and GVWR",
                "why": "Neither the designed seating capacity nor the weight rating is on file."}

    heavy = bool(gvwr and gvwr >= HEAVY_GVWR)
    passengers = bool(seats and seats >= PASSENGER_SEATS)
    if not heavy and not passengers:
        return {"known": True, "cdl": None, "endorsement": None,
                "summary": "No commercial license needed",
                # Named precisely, because these are the thresholds for a commercial LICENSE and
                # not the ones that decide whether the vehicle is a commercial motor vehicle. A van
                # rated 26,000 lb is comfortably a commercial motor vehicle and still needs no CDL,
                # and saying it is "under both commercial thresholds" reads as a contradiction.
                "why": (f"Carries {seats} including the driver, under 16" if seats else "")
                       + ("; " if seats and gvwr else "")
                       + (f"rated {gvwr:,} lb, under 26,001" if gvwr else "")
                       + " - the two thresholds that call for a commercial license."}

    cdl = "B" if heavy else "C"
    why = []
    if passengers:
        why.append(f"designed for {seats} including the driver, which is more than 15")
    if heavy:
        why.append(f"rated {gvwr:,} lb, which is 26,001 or more")
    return {
        "known": True, "cdl": cdl, "endorsement": "P" if passengers else None,
        "summary": f"Class {cdl} CDL" + (" with a passenger (P) endorsement" if passengers else ""),
        "why": "This vehicle is " + " and ".join(why) + ".",
    }


###################################################################################################
# Whether the vehicle is a commercial motor vehicle - which is two questions, not one.
#
# The federal test and the Florida test disagree, and for an NEMT fleet they disagree in the case
# that matters most. A twelve-seat van carrying passengers for hire is a commercial motor vehicle
# under 49 CFR 390.5(2) and is not one under F.S. 316.003(14), because Florida has no compensation
# prong. Everything downstream turns on that: Part 391 reaches the first, F.S. 316.302 never
# engages for the second.
#
# Nothing here guesses. A fact we cannot reach from what is recorded comes back None, which is a
# different answer from False and has to stay different - "we have not asked" is not "no".
###################################################################################################
FED_WEIGHT = 10_001           # 49 CFR 390.5(1) - GVWR or GCWR, whichever is greater
FL_WEIGHT = 10_000            # F.S. 316.003(14)(a) - one pound lower than the federal line
FED_HIRE_SEATS = 9            # 390.5(2) - more than 8 including the driver, for compensation
FED_FREE_SEATS = 16           # 390.5(3) - more than 15 including the driver, not for compensation
FL_SEATS = 16                 # 316.003(14)(b) - more than 15, compensation irrelevant


def _weight(vehicle: dict) -> int | None:
    """The heavier of the two ratings, which is how 390.5 reads them."""
    known = [v for v in (vehicle.get("gvwr"), vehicle.get("gcwr")) if v]
    return max(known) if known else None


def facts(vehicle: dict) -> dict:
    """The derived facts about one vehicle, each with the reason it came out that way.

    These are conclusions and are never stored. A person who can tick "this is a commercial motor
    vehicle" will eventually tick it wrong, and the engine would believe them."""
    seats, weight = vehicle.get("seats"), _weight(vehicle)
    hire = vehicle.get("forcompensation")
    hire = True if hire is None else bool(hire)

    # Each test reports what it found either way, so a "No" is as specific as a "Yes". A reason
    # that only ever names the thresholds a vehicle CLEARED is how the panel came to say a 26,000 lb
    # van was a commercial motor vehicle and, in the next breath, under every threshold.
    def settle(tests: list[tuple[bool, str]], needed: list) -> tuple[bool | None, str]:
        met = [why for hit, why in tests if hit]
        if met:
            return True, ("Rated" + "; ".join(met)[5:] if met[0].startswith("rated")
                          else met[0][0].upper() + met[0][1:] + "".join("; " + m for m in met[1:])) + "."
        if any(v is None for v in needed):
            missing = [n for n, v in (("the seating capacity", seats),
                                      ("the weight rating", vehicle.get("gvwr"))) if not v]
            return None, f"Not enough recorded to say - {' and '.join(missing)} is missing."
        unmet = [why for hit, why in tests if not hit]
        return False, unmet[0][0].upper() + unmet[0][1:] + "".join("; " + m for m in unmet[1:]) + "."

    # Federal. Weight counts either rating; the passenger prong depends on compensation.
    tests = [
        (bool(weight and weight >= FED_WEIGHT),
         f"rated {weight:,} lb, which is {FED_WEIGHT:,} or more - 49 CFR 390.5(1)"
         if weight and weight >= FED_WEIGHT
         else f"rated {weight:,} lb, which is under {FED_WEIGHT:,} - 49 CFR 390.5(1)" if weight
         else f"no weight rating of {FED_WEIGHT:,} lb or more - 49 CFR 390.5(1)"),
    ]
    if hire:
        tests.append((bool(seats and seats >= FED_HIRE_SEATS),
                      f"carries {seats} including the driver for compensation, which is more than 8"
                      " - 49 CFR 390.5(2)" if seats and seats >= FED_HIRE_SEATS
                      else f"carries {seats} including the driver for compensation, which is not more"
                           " than 8 - 49 CFR 390.5(2)"))
    else:
        tests.append((bool(seats and seats >= FED_FREE_SEATS),
                      f"carries {seats} including the driver, which is more than 15 - 49 CFR 390.5(3)"
                      if seats and seats >= FED_FREE_SEATS
                      else f"carries {seats} including the driver and not for compensation, which is"
                           " not more than 15 - 49 CFR 390.5(3)"))
    cmv_federal, fed_why = settle(tests, [seats, vehicle.get("gvwr")])

    # Florida. No compensation prong at all, and a pound lighter.
    gvwr = vehicle.get("gvwr")
    cmv_florida, fl_why = settle([
        (bool(gvwr and gvwr >= FL_WEIGHT),
         f"rated {gvwr:,} lb, which is {FL_WEIGHT:,} or more - F.S. 316.003(14)(a)" if gvwr and gvwr >= FL_WEIGHT
         else f"rated {gvwr:,} lb, which is under {FL_WEIGHT:,} - F.S. 316.003(14)(a)" if gvwr
         else f"no weight rating of {FL_WEIGHT:,} lb or more - F.S. 316.003(14)(a)"),
        (bool(seats and seats >= FL_SEATS),
         f"carries {seats} including the driver, which is more than 15 - F.S. 316.003(14)(b)"
         if seats and seats >= FL_SEATS
         else f"carries {seats} including the driver, which is not more than 15 - F.S. 316.003(14)(b)"),
    ], [seats, gvwr])

    # Worked out here rather than read off license_for, which answers a different question: it says
    # what license to ask a driver for and settles for what it knows, so a vehicle with a weight on
    # file and no seating count comes back "no commercial license needed". For a fact the engine
    # will act on, a missing seating count has to stay unknown - a twenty-seat bus and a seven-seat
    # van weigh the same on paper until somebody counts the seats.
    cdl_required, cdl_why = settle([
        (bool(weight and weight >= HEAVY_GVWR),
         f"rated {weight:,} lb, which is {HEAVY_GVWR:,} or more - 49 CFR 383.91(a)(2)"
         if weight and weight >= HEAVY_GVWR
         else f"rated {weight:,} lb, which is under {HEAVY_GVWR:,} - 49 CFR 383.91(a)(2)" if weight
         else f"no weight rating of {HEAVY_GVWR:,} lb or more - 49 CFR 383.91(a)(2)"),
        (bool(seats and seats >= PASSENGER_SEATS),
         f"carries {seats} including the driver, which is 16 or more - 49 CFR 383.91(a)(3)"
         if seats and seats >= PASSENGER_SEATS
         else f"carries {seats} including the driver, which is under 16 - 49 CFR 383.91(a)(3)"),
    ], [seats, vehicle.get("gvwr")])

    return {
        "cmv_federal": cmv_federal,
        "cmv_florida": cmv_florida,
        "cdl_required": cdl_required,
        "forcompensation": hire,
        "license": license_for(vehicle),
        "why": {"cmv_federal": fed_why, "cmv_florida": fl_why, "cdl_required": cdl_why},
    }
