import random
from decimal import Decimal
from typing import Tuple, Optional
from dataclasses import dataclass

@dataclass
class GameResult:
    won: bool
    draw: bool
    amount: Decimal
    message: str
    emoji: str
    value: Optional[int] = None

class Game:
    EMOJI = "🎲"
    
    def __init__(self, bet_amount: Decimal):
        self.bet_amount = bet_amount

    async def process(self, bet_type: str, dice_value: int) -> GameResult:
        raise NotImplementedError

    def get_emoji(self, bet_type: str) -> str:
        return self.EMOJI

class CubeGame(Game):
    EMOJI = "🎲"
    
    async def process(self, bet_type: str, dice_value: int) -> GameResult:
        bet_type = bet_type.lower().replace(" ", "")
        
        if bet_type in ["чет", "нечет"]:
            is_even = dice_value % 2 == 0
            if (bet_type == "чет" and is_even) or (bet_type == "нечет" and not is_even):
                win_amount = self.bet_amount * Decimal('1.85')
                return GameResult(
                    won=True,
                    draw=False,
                    amount=win_amount,
                    message=f"🎲 Выпало число {dice_value}!\nВы выиграли {win_amount}$!",
                    emoji=self.EMOJI,
                    value=dice_value
                )
        
        elif bet_type in ["больше", "меньше"]:
            if (bet_type == "больше" and dice_value > 3) or (bet_type == "меньше" and dice_value <= 3):
                win_amount = self.bet_amount * Decimal('1.85')
                return GameResult(
                    won=True,
                    draw=False,
                    amount=win_amount,
                    message=f"🎲 Выпало число {dice_value}!\nВы выиграли {win_amount}$!",
                    emoji=self.EMOJI,
                    value=dice_value
                )
        
        elif bet_type in ["сектор1", "сектор2", "сектор3", "с1", "с2", "с3"]:
            sector_map = {
                "сектор1": "1", "с1": "1",
                "сектор2": "2", "с2": "2",
                "сектор3": "3", "с3": "3"
            }
            sector = sector_map[bet_type]
            sector_numbers = {
                "1": [1, 2],
                "2": [3, 4],
                "3": [5, 6]
            }
            if dice_value in sector_numbers[sector]:
                win_amount = self.bet_amount * Decimal('2.5')
                return GameResult(
                    won=True,
                    draw=False,
                    amount=win_amount,
                    message=f"🎲 Выпало число {dice_value}!\nСектор {sector} выиграл!\nВы выиграли {win_amount}$!",
                    emoji=self.EMOJI,
                    value=dice_value
                )
        
        elif bet_type in ["1", "2", "3", "4", "5", "6"]:
            if str(dice_value) == bet_type:
                win_amount = self.bet_amount * Decimal('4')
                return GameResult(
                    won=True,
                    draw=False,
                    amount=win_amount,
                    message=f"🎲 Выпало число {dice_value}!\nВы выиграли {win_amount}$!",
                    emoji=self.EMOJI,
                    value=dice_value
                )
        
        elif bet_type in ["плинко", "пл", "plinko"]:
            multipliers = {1: 0, 2: Decimal('0.3'), 3: Decimal('0.9'), 
                         4: Decimal('1.1'), 5: Decimal('1.4'), 6: Decimal('1.95')}
            if dice_value in multipliers and multipliers[dice_value] > 0:
                win_amount = self.bet_amount * multipliers[dice_value]
                return GameResult(
                    won=True,
                    draw=False,
                    amount=win_amount,
                    message=f"🎲 Выпало число {dice_value}!\nВы выиграли {win_amount}$!",
                    emoji=self.EMOJI,
                    value=dice_value
                )

        return GameResult(
            won=False,
            draw=False,
            amount=Decimal('0'),
            message=f"🎲 Выпало число {dice_value}!\nВы проиграли!",
            emoji=self.EMOJI,
            value=dice_value
        )

class TwoDiceGame(Game):
    EMOJI = "🎲"
    
    async def process(self, bet_type: str, dice_value: int, second_dice_value: int = None) -> GameResult:
        bet_type = bet_type.lower().replace(" ", "")
        dice1 = dice_value
        dice2 = second_dice_value if second_dice_value is not None else await self.roll_second_dice()
        if bet_type == "ничья":
            if dice1 == dice2:
                return GameResult(True, False, self.bet_amount * Decimal('3'), f"🎲 Выпало {dice1} и {dice2}! Ничья — выигрыш {self.bet_amount * Decimal('3')}$!", self.EMOJI, dice_value)
            else: 
                return GameResult(False, False, Decimal('0'), f"🎲 Выпало {dice1} и {dice2}!\nВы проиграли!", self.EMOJI, dice_value)
        elif bet_type == "победа1":
            if dice1 > dice2:
                return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🎲 Выпало {dice1} и {dice2}!\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
            elif dice1 == dice2:
                return GameResult(False, True, self.bet_amount * Decimal('1'), f"🎲 Выпало {dice1} и {dice2}! Ничья — {self.bet_amount}$", self.EMOJI, dice_value)
            else:
                return GameResult(False, False, Decimal('0'), f"🎲 Выпало {dice1} и {dice2}!\nВы проиграли!", self.EMOJI, dice_value)
        elif bet_type == "победа2":
            if dice2 > dice1:
                return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🎲 Выпало {dice1} и {dice2}!\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
            elif dice1 == dice2:
                return GameResult(True, True, self.bet_amount * Decimal('1'), f"🎲 Выпало {dice1} и {dice2}! Ничья — возврат {self.bet_amount}$", self.EMOJI, dice_value)
            else:
                return GameResult(False, False, Decimal('0'), f"🎲 Выпало {dice1} и {dice2}!\nВы проиграли!", self.EMOJI, dice_value)
        return GameResult(False, Decimal('0'), f"🎲 Выпало {dice1} и {dice2}!\nВы проиграли!", self.EMOJI, dice_value)
    
    async def roll_second_dice(self) -> int:
        return random.randint(1, 6)

class RockPaperScissorsGame(Game):
    EMOJI = "👊"
    

    ROCK_EMOJI = "👊"
    PAPER_EMOJI = "✋"
    SCISSORS_EMOJI = "✌️"

    BET_EMOJIS = {
        "камень": ROCK_EMOJI,
        "бумага": PAPER_EMOJI,
        "ножницы": SCISSORS_EMOJI,
        "rock": ROCK_EMOJI,
        "paper": PAPER_EMOJI,
        "scissors": SCISSORS_EMOJI,
        "к": ROCK_EMOJI,
        "б": PAPER_EMOJI,
        "н": SCISSORS_EMOJI,
        "r": ROCK_EMOJI,
        "p": PAPER_EMOJI,
        "s": SCISSORS_EMOJI,
    }
    
    RULES = {
        "камень": ["ножницы"],
        "бумага": ["камень"],
        "ножницы": ["бумага"],
    }
    
    def get_emoji(self, bet_type: str) -> str:
        bet_type = bet_type.lower().replace(" ", "")
        return self.BET_EMOJIS.get(bet_type, self.EMOJI)
    
    async def process(self, bet_type: str, bot_choice_value: int) -> GameResult:
        bet_type = bet_type.lower().replace(" ", "")
        
        bet_mapping = {
            "к": "камень", "б": "бумага", "н": "ножницы",
            "r": "камень", "p": "бумага", "s": "ножницы",
            "rock": "камень", "paper": "бумага", "scissors": "ножницы"
        }
        
        player_choice = bet_mapping.get(bet_type, bet_type)
        
        if player_choice not in ["камень", "бумага", "ножницы"]:
            return GameResult(
                won=False,
                draw=False,
                amount=Decimal('0'),
                message=f"❌",
                emoji=self.EMOJI,
                value=bot_choice_value
            )
        
        bot_choices = {1: "камень", 2: "ножницы", 3: "бумага"}
        bot_choice = bot_choices.get(bot_choice_value, "камень")
        
        player_emoji = self.BET_EMOJIS[player_choice]
        bot_emoji = self.BET_EMOJIS[bot_choice]
        
        if player_choice == bot_choice:
            win_amount = self.bet_amount * Decimal('1')
            return GameResult(
                won=True,
                draw=True,
                amount=win_amount,
                message=f"{player_emoji}",
                emoji=self.EMOJI,
                value=bot_choice_value
            )
        
        elif bot_choice in self.RULES.get(player_choice, []):
            win_amount = self.bet_amount * Decimal('2.5')
            return GameResult(
                won=True,
                draw=False,
                amount=win_amount,
                message=f"{player_emoji}",
                emoji=self.EMOJI,
                value=bot_choice_value
            )
        
        else:
            return GameResult(
                won=False,
                draw=False,
                amount=Decimal('0'),
                message=f"{player_emoji}",
                emoji=self.EMOJI,
                value=bot_choice_value
            ) 

class BasketballGame(Game):
    EMOJI = "🏀"
    
    async def process(self, bet_type: str, dice_value: int) -> GameResult:
        bet_type = bet_type.lower().replace(" ", "")
        goal_words = ["гол", "попадание", "goal", "hit", "score"]
        miss_words = ["промах", "мимо", "miss"]
        is_goal = dice_value in [4, 5]
        if any(word in bet_type for word in goal_words) and is_goal:
            return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🏀 Попадание! Выпало {dice_value}\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
        if any(word in bet_type for word in miss_words) and not is_goal:
            return GameResult(True, self.bet_amount * Decimal('1.4'), f"🏀 Промах! Выпало {dice_value}\nВы выиграли {self.bet_amount * Decimal('1.4')}$!", self.EMOJI, dice_value)
        return GameResult(False, False, Decimal('0'), f"🏀 Выпало {dice_value}\nВы проиграли!", self.EMOJI, dice_value)

class DartsGame(Game):
    EMOJI = "🎯"
    
    async def process(self, bet_type: str, dice_value: int) -> GameResult:
        bet_type = bet_type.lower().replace(" ", "")
        miss_words = ["промах", "мимо"]
        white_words = ["белое"]
        red_words = ["красное"]
        bullseye_words = ["яблочко"]
        if bet_type in miss_words:
            if dice_value == 1:
                return GameResult(True, False, self.bet_amount * Decimal('2.5'), f"🎯 Промах! Выпало {dice_value}\nВы выиграли {self.bet_amount * Decimal('2.5')}$!", self.EMOJI, dice_value)
            else:
                return GameResult(False, False, Decimal('0'), f"🎯 Выпало {dice_value}\nВы проиграли!", self.EMOJI, dice_value)
        if bet_type in white_words:
            if dice_value in [3, 5]:
                return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🎯 Белое! Выпало {dice_value}\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
            else:
                return GameResult(False, False, Decimal('0'), f"🎯 Выпало {dice_value}\nВы проиграли!", self.EMOJI, dice_value)
        if bet_type in red_words:
            if dice_value in [2, 4]:
                return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🎯 Красное! Выпало {dice_value}\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
            else:
                return GameResult(False, False, Decimal('0'), f"🎯 Выпало {dice_value}\nВы проиграли!", self.EMOJI, dice_value)
        if bet_type in bullseye_words:
            if dice_value == 6:
                return GameResult(True, False, self.bet_amount * Decimal('2.5'), f"🎯 Яблочко! Выпало {dice_value}\nВы выиграли {self.bet_amount * Decimal('2.5')}$!", self.EMOJI, dice_value)
            else:
                return GameResult(False, Decimal('0'), f"🎯 Выпало {dice_value}\nВы проиграли!", self.EMOJI, dice_value)
        return GameResult(False, Decimal('0'), f"🎯 Выпало {dice_value}\nВы проиграли!", self.EMOJI, dice_value)

class SlotsGame(Game):
    EMOJI = "🎰"
    
    async def process(self, bet_type: str, dice_value: int) -> GameResult:
        # 64 — три семёрки (x10)
        # 1 — три BAR (x5)
        # 43, 22, 52, 27, 38 — три одинаковых (x5)
        if dice_value == 64:
            return GameResult(True, False, self.bet_amount * Decimal('10'), f"🎰 Джекпот! 777!\nВы выиграли {self.bet_amount * Decimal('10')}$!", self.EMOJI, dice_value)
        if dice_value == 1:
            return GameResult(True, False, self.bet_amount * Decimal('5'), f"🎰 Джекпот! BAR!\nВы выиграли {self.bet_amount * Decimal('5')}$!", self.EMOJI, dice_value)
        if dice_value in [43, 22, 52, 27, 38]:
            return GameResult(True, False, self.bet_amount * Decimal('5'), f"🎰 Три одинаковых!\nВы выиграли {self.bet_amount * Decimal('5')}$!", self.EMOJI, dice_value)
        return GameResult(False, Decimal('0'), f"🎰 Неудачная комбинация.\nВы проиграли!", self.EMOJI, dice_value)
    
class BowlingGame(Game):
    EMOJI = "🎳"
    
    async def process(self, bet_type: str, dice_value: int, second_dice_value: int = None) -> GameResult:
        bet_type = bet_type.lower().replace(" ", "")
        duel_words = ["боулпобеда", "боулпоражение"]
        strike_words = ["страйк"]
        miss_words = ["боулпромах"]
        # Дуэль
        if bet_type in duel_words and second_dice_value is not None:
            if bet_type == "боулпобеда":
                if dice_value > (second_dice_value or 0):
                    return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🎳 Дуэль: {dice_value} vs {second_dice_value}\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
                elif dice_value == (second_dice_value or 0):
                    return GameResult(True, True, self.bet_amount * Decimal('1'), f"🎳 Дуэль: {dice_value} vs {second_dice_value}! Ничья — ставка возвращается с комиссией 30%: {self.bet_amount * Decimal('0.7')}$!", self.EMOJI, dice_value)
                else:
                    return GameResult(False, False, Decimal('0'), f"🎳 Дуэль: {dice_value} vs {second_dice_value}\nВы проиграли!", self.EMOJI, dice_value)
            if bet_type == "боулпоражение":
                if dice_value < (second_dice_value or 0):
                    return GameResult(True, False, self.bet_amount * Decimal('1.85'), f"🎳 Дуэль: {dice_value} vs {second_dice_value}\nВы выиграли {self.bet_amount * Decimal('1.85')}$!", self.EMOJI, dice_value)
                elif dice_value == (second_dice_value or 0):
                    return GameResult(True, True, self.bet_amount * Decimal('1'), f"🎳 Дуэль: {dice_value} vs {second_dice_value}! Ничья — ставка возвращается с комиссией 30%: {self.bet_amount * Decimal('0.7')}$!", self.EMOJI, dice_value)
                else:
                    return GameResult(False, False, Decimal('0'), f"🎳 Дуэль: {dice_value} vs {second_dice_value}\nВы проиграли!", self.EMOJI, dice_value)
        # Одиночный режим (Plinko-стиль)
        if bet_type in ["боул", "боулинг"]:
            if dice_value == 0:
                return GameResult(True, False, self.bet_amount * Decimal('4'), f"🎳 Промах! Выпало {dice_value}. Выигрыш x4!", self.EMOJI, dice_value)
            elif dice_value == 1:
                return GameResult(False, False, Decimal('0'), f"🎳 Выпало {dice_value}. Поражение!", self.EMOJI, dice_value)
            elif dice_value == 6:
                return GameResult(True, False, self.bet_amount * Decimal('4'), f"🎳 Страйк! Выпало {dice_value}. Выигрыш x4!", self.EMOJI, dice_value)
            else:
                return GameResult(True, False, self.bet_amount * Decimal('1.4'), f"🎳 Обычный бросок! Выпало {dice_value}. Выигрыш x1.4!", self.EMOJI, dice_value)
        if bet_type in strike_words and dice_value == 6:
            return GameResult(True, False, self.bet_amount * Decimal('4'), f"🎳 Страйк! Выпало {dice_value}. Вы выиграли {self.bet_amount * Decimal('4')}$!", self.EMOJI, dice_value)
        if bet_type in miss_words and dice_value == 0:
            return GameResult(True, False, self.bet_amount * Decimal('4'), f"🎳 Промах! Выпало {dice_value}. Вы выиграли {self.bet_amount * Decimal('4')}$!", self.EMOJI, dice_value)
        return GameResult(False, False, Decimal('0'), f"🎳 Выпало {dice_value}. Вы проиграли!", self.EMOJI, dice_value) 